"""
services/upload.py 测试套件。

覆盖场景：
- 扩展名白名单校验（.txt / .pdf / .docx，大小写不敏感）
- 文件大小校验（超过 MAX_UPLOAD_SIZE_MB 抛 HTTP 413）
- 空文件（0 字节）校验（抛 HTTP 400）
- 正常上传返回 stored_path 和 file_size
- 目录不存在时自动创建
- 不校验文件内容是否损坏（由 extract.py 阶段处理）
"""
import io
import pytest
from pathlib import Path

from fastapi import UploadFile
from fastapi.testclient import TestClient


class TestUploadFileValidation:
    """文件扩展名和大小校验。"""

    def test_upload_valid_txt(self, test_client: TestClient, db_session, upload_dir: Path):
        """.txt 文件扩展名合法，上传成功。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        files = {"file": ("bid.txt", io.BytesIO(b"Hello world"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201
        assert res.json()["original_filename"] == "bid.txt"

    def test_upload_valid_pdf(self, test_client: TestClient, db_session, upload_dir: Path):
        """.pdf 文件扩展名合法，上传成功。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        files = {"file": ("bid.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201
        assert res.json()["original_filename"] == "bid.pdf"

    def test_upload_valid_docx(self, test_client: TestClient, db_session, upload_dir: Path):
        """.docx 文件扩展名合法，上传成功。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        files = {"file": ("bid.docx", io.BytesIO(b"PK\x03\x04"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201
        assert res.json()["original_filename"] == "bid.docx"

    def test_upload_uppercase_extension(self, test_client: TestClient, db_session, upload_dir: Path):
        """.TXT / .PDF / .DOCX 大写扩展名，大小写不敏感，应成功。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        files = {"file": ("bid.TXT", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201

    def test_upload_invalid_extension(self, test_client: TestClient, db_session, upload_dir: Path):
        """不在白名单的扩展名（.jpg / .exe / .zip）返回 400。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        for ext in [".jpg", ".exe", ".zip", ".doc", ".png"]:
            files = {"file": (f"bid{ext}", io.BytesIO(b"content"), "application/octet-stream")}
            data = {"supplier_name": "Supplier A"}
            res = test_client.post(
                f"/api/v1/tasks/{task_id}/documents",
                files=files,
                data=data,
            )
            assert res.status_code == 400, f"Extension {ext} should be rejected"

    def test_upload_empty_file(self, test_client: TestClient, db_session, upload_dir: Path):
        """空文件（0 字节）返回 400。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 400

    def test_upload_file_too_large(self, test_client: TestClient, db_session, upload_dir: Path):
        """文件大小超过 MAX_UPLOAD_SIZE_MB (50MB) 返回 413。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        # 生成 51MB 文件（超过 50MB 限制）
        large_content = b"x" * (51 * 1024 * 1024)
        files = {"file": ("large.txt", io.BytesIO(large_content), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 413

    def test_upload_file_exactly_at_limit(self, test_client: TestClient, db_session, upload_dir: Path):
        """文件大小恰好等于 50MB 时应成功。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        # 精确 50MB
        content = b"x" * (50 * 1024 * 1024)
        files = {"file": ("exact.txt", io.BytesIO(content), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201


class TestUploadStorage:
    """文件存储逻辑。"""

    def test_stored_path_format(self, test_client: TestClient, db_session, upload_dir: Path):
        """stored_path 格式为 {task_id}/{uuid}{ext}。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        files = {"file": ("bid.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201
        stored_path = res.json()["stored_path"]
        # 格式：{task_id}/{uuid}.pdf
        parts = stored_path.split("/")
        assert len(parts) == 2
        assert parts[0] == str(task_id)
        assert parts[1].endswith(".pdf")

    def test_file_saved_to_disk(self, test_client: TestClient, db_session, upload_dir: Path):
        """文件确实写入磁盘，磁盘路径可读。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        content = b"Test file content for disk verification."
        files = {"file": ("bid.txt", io.BytesIO(content), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        stored_path = res.json()["stored_path"]
        full_path = upload_dir / stored_path

        assert full_path.exists()
        assert full_path.read_bytes() == content

    def test_directory_created_automatically(self, test_client: TestClient, db_session, upload_dir: Path):
        """task_id 目录不存在时自动创建。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        task_dir = upload_dir / str(task_id)
        assert not task_dir.exists()  # 上传前目录不存在

        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201
        assert task_dir.exists()

    def test_file_size_recorded(self, test_client: TestClient, db_session, upload_dir: Path):
        """返回的 file_size 与实际文件字节数一致。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        content = b"a" * 12345
        files = {"file": ("bid.txt", io.BytesIO(content), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201
        assert res.json()["file_size"] == 12345


class TestUploadBusinessRules:
    """业务规则校验。"""

    def test_upload_to_nonexistent_task(self, test_client: TestClient, db_session, upload_dir: Path):
        """上传到不存在的 task_id 返回 404。"""
        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            "/api/v1/tasks/99999/documents",
            files=files,
            data=data,
        )
        assert res.status_code == 404

    def test_upload_to_completed_task(self, test_client: TestClient, db_session, upload_dir: Path):
        """上传到已完成的任务（completed）返回 400。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        # 手动将任务状态改为 completed
        from app.models.models import Task
        from app.schemas.schemas import TaskStatus
        task = db_session.get(Task, task_id)
        task.status = TaskStatus.completed
        db_session.commit()

        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )
        assert res.status_code == 400

    def test_upload_to_processing_task(self, test_client: TestClient, db_session, upload_dir: Path):
        """上传到处理中的任务（processing）返回 400。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        from app.models.models import Task
        from app.schemas.schemas import TaskStatus
        task = db_session.get(Task, task_id)
        task.status = TaskStatus.processing
        db_session.commit()

        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )
        assert res.status_code == 400

    def test_upload_to_pending_task_success(self, test_client: TestClient, db_session, upload_dir: Path):
        """上传到 pending 状态的任务成功。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )
        assert res.status_code == 201

    def test_multiple_uploads_same_task(self, test_client: TestClient, db_session, upload_dir: Path):
        """同一任务可上传多份文件。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        for i in range(3):
            files = {"file": (f"bid_{i}.txt", io.BytesIO(b"content"), "text/plain")}
            data = {"supplier_name": f"Supplier {i}"}
            res = test_client.post(
                f"/api/v1/tasks/{task_id}/documents",
                files=files,
                data=data,
            )
            assert res.status_code == 201

        # 确认文档数量
        task_res = test_client.get(f"/api/v1/tasks/{task_id}")
        assert len(task_res.json()["documents"]) == 3

    def test_supplier_name_required(self, test_client: TestClient, db_session, upload_dir: Path):
        """supplier_name 为空或缺失返回 422。"""
        task_res = test_client.post("/api/v1/tasks", json={"name": "Test Task"})
        task_id = task_res.json()["id"]

        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": ""}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )
        # FastAPI Pydantic 校验：min_length=1 -> 422
        assert res.status_code == 422
