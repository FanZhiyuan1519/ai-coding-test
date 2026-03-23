"""
pytest 配置：测试数据库、fixtures、客户端。
使用 SQLite 内存数据库，不依赖真实 PostgreSQL。
每个测试结束后回滚事务，保证测试间完全隔离。

conftest 在实现代码之前加载，所有延迟导入均在 fixture 内部完成。
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AI_ENABLED"] = "false"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="bid_test_uploads_")


# ── 测试用临时上传目录 ──────────────────────────────────────────────────────
_test_upload_root: Path = Path(tempfile.mkdtemp(prefix="bid_test_uploads_"))


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_uploads():
    yield
    shutil.rmtree(_test_upload_root, ignore_errors=True)


@pytest.fixture
def upload_dir() -> "Path":
    test_dir = _test_upload_root / f"test_{os.getpid()}_{id(object())}"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    if test_dir.exists():
        for item in test_dir.iterdir():
            if item.is_file():
                item.unlink()


# ── 测试数据库（SQLite in-memory） ─────────────────────────────────────────
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _recreate_tables() -> None:
    from app.models.models import Base

    with _engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            table.drop(bind=conn, checkfirst=True)
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.commit()
    Base.metadata.create_all(bind=_engine)


@pytest.fixture(scope="function")
def db_engine():
    _recreate_tables()
    yield _engine


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = _TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ── TestClient ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def test_client(db_session: Session, upload_dir: Path) -> Generator[TestClient, None, None]:
    from app.main import app
    from app.core.database import get_db
    from app.core.config import get_settings

    original_upload_dir = os.environ.get("UPLOAD_DIR")
    original_ai_enabled = os.environ.get("AI_ENABLED")
    original_max_size = os.environ.get("MAX_UPLOAD_SIZE_MB")

    os.environ["UPLOAD_DIR"] = str(upload_dir)
    os.environ["AI_ENABLED"] = "false"
    os.environ["MAX_UPLOAD_SIZE_MB"] = "50"

    get_settings.cache_clear()

    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    if original_upload_dir is not None:
        os.environ["UPLOAD_DIR"] = original_upload_dir
    else:
        os.environ.pop("UPLOAD_DIR", None)

    if original_ai_enabled is not None:
        os.environ["AI_ENABLED"] = original_ai_enabled
    else:
        os.environ.pop("AI_ENABLED", None)

    if original_max_size is not None:
        os.environ["MAX_UPLOAD_SIZE_MB"] = original_max_size
    else:
        os.environ.pop("MAX_UPLOAD_SIZE_MB", None)

    app.dependency_overrides.clear()


# ── 辅助 fixtures ──────────────────────────────────────────────────────────
@pytest.fixture
def sample_txt_file(upload_dir: Path) -> tuple[Path, bytes]:
    content = (
        b"Test Supplier Company Ltd.\n"
        b"Address: Beijing Chaoyang District, No.123\n"
        b"Phone: 010-12345678\n"
        b"Unified Social Credit Code: 91110000MA00ABCD01\n"
        b"Legal Representative: Zhang San\n"
    )
    return upload_dir / "test.txt", content


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000058 00000 n\n"
        b"0000000115 00000 n\n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n194\n"
        b"%%EOF"
    )


@pytest.fixture
def sample_docx_bytes() -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>',
        )
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<w:body>"
            '<w:p><w:r><w:t>Supplier Company Document</w:t></w:r></w:p>'
            "</w:body>"
            "</w:document>",
        )
    buf.seek(0)
    return buf.read()
