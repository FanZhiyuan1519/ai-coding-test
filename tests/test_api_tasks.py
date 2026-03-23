"""
/api/v1/tasks 路由测试套件。

覆盖场景：
- GET /health: 健康检查
- POST /tasks: 正常创建、name 为空返回 422
- GET /tasks: 分页正确、total 和 total_pages 计算正确
- GET /tasks/{id}: 返回 documents 列表、不存在返回 404
- DELETE /tasks/{id}: 磁盘文件被删除、数据库记录被删除、顺序正确（无外键）
- POST /tasks/{id}/documents: 上传成功、格式不支持返回 400、超过 50MB 返回 413、0 字节返回 400、任务不存在返回 404、completed 状态返回 400
- POST /tasks/{id}/run: 正常触发返回 202、文件数 < 2 返回 400、processing 状态返回 409
"""
import io
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


class TestHealth:
    """GET /health — 健康检查。"""

    def test_health_returns_ok(self, test_client: TestClient):
        """健康检查返回 {"status": "ok"}"""
        res = test_client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


class TestCreateTask:
    """POST /api/v1/tasks — 创建任务。"""

    def test_create_task_success(self, test_client: TestClient):
        """正常创建任务，返回 201 和 TaskDetailResponse。"""
        res = test_client.post("/api/v1/tasks", json={"name": "2024年办公用品采购比对"})
        assert res.status_code == 201

        body = res.json()
        assert body["id"] is not None
        assert body["name"] == "2024年办公用品采购比对"
        assert body["status"] == "pending"
        assert body["progress"] == 0
        assert body["error_message"] is None
        assert body["documents"] == []

    def test_create_task_with_empty_name(self, test_client: TestClient):
        """name 为空字符串返回 422（Pydantic min_length 校验）。"""
        res = test_client.post("/api/v1/tasks", json={"name": ""})
        assert res.status_code == 422

    def test_create_task_missing_name(self, test_client: TestClient):
        """name 字段缺失返回 422。"""
        res = test_client.post("/api/v1/tasks", json={})
        assert res.status_code == 422

    def test_create_task_name_too_long(self, test_client: TestClient):
        """name 超过 255 字符返回 422。"""
        res = test_client.post("/api/v1/tasks", json={"name": "x" * 256})
        assert res.status_code == 422


class TestListTasks:
    """GET /api/v1/tasks — 任务列表。"""

    def test_list_tasks_empty(self, test_client: TestClient):
        """无任务时返回空列表。"""
        res = test_client.get("/api/v1/tasks")
        assert res.status_code == 200

        body = res.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["page"] == 1
        assert body["limit"] == 10
        assert body["total_pages"] == 0

    def test_list_tasks_pagination(self, test_client: TestClient):
        """分页参数 page=1&limit=2 正确。"""
        # 创建 3 个任务
        for i in range(3):
            test_client.post("/api/v1/tasks", json={"name": f"Task {i}"})

        res = test_client.get("/api/v1/tasks?page=1&limit=2")
        assert res.status_code == 200

        body = res.json()
        assert len(body["items"]) == 2
        assert body["total"] == 3
        assert body["page"] == 1
        assert body["limit"] == 2
        assert body["total_pages"] == 2

    def test_list_tasks_second_page(self, test_client: TestClient):
        """page=2 时返回剩余任务。"""
        for i in range(3):
            test_client.post("/api/v1/tasks", json={"name": f"Task {i}"})

        res = test_client.get("/api/v1/tasks?page=2&limit=2")
        body = res.json()
        assert len(body["items"]) == 1
        assert body["page"] == 2

    def test_list_tasks_default_pagination(self, test_client: TestClient):
        """无参数时默认 page=1, limit=10。"""
        res = test_client.get("/api/v1/tasks")
        body = res.json()
        assert body["page"] == 1
        assert body["limit"] == 10

    def test_list_tasks_invalid_page(self, test_client: TestClient):
        """page < 1 时返回 422。"""
        res = test_client.get("/api/v1/tasks?page=0")
        assert res.status_code == 422

    def test_list_tasks_invalid_limit(self, test_client: TestClient):
        """limit > 100 时返回 422。"""
        res = test_client.get("/api/v1/tasks?limit=101")
        assert res.status_code == 422

    def test_list_tasks_document_count(self, test_client: TestClient):
        """列表项包含 document_count。"""
        # 创建任务并上传 2 份文件
        res = test_client.post("/api/v1/tasks", json={"name": "Task with docs"})
        task_id = res.json()["id"]

        for i in range(2):
            files = {"file": (f"bid_{i}.txt", io.BytesIO(b"content"), "text/plain")}
            data = {"supplier_name": f"Supplier {i}"}
            test_client.post(f"/api/v1/tasks/{task_id}/documents", files=files, data=data)

        res = test_client.get("/api/v1/tasks")
        items = res.json()["items"]
        task_item = next(item for item in items if item["id"] == task_id)
        assert task_item["document_count"] == 2


class TestGetTask:
    """GET /api/v1/tasks/{task_id} — 任务详情。"""

    def test_get_task_success(self, test_client: TestClient):
        """获取任务详情，包含 documents 列表。"""
        # 创建任务
        res = test_client.post("/api/v1/tasks", json={"name": "Detail Test"})
        task_id = res.json()["id"]

        # 上传文件
        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        test_client.post(f"/api/v1/tasks/{task_id}/documents", files=files, data=data)

        res = test_client.get(f"/api/v1/tasks/{task_id}")
        assert res.status_code == 200

        body = res.json()
        assert body["id"] == task_id
        assert body["name"] == "Detail Test"
        assert body["status"] == "pending"
        assert len(body["documents"]) == 1
        assert body["documents"][0]["supplier_name"] == "Supplier A"

    def test_get_task_not_found(self, test_client: TestClient):
        """不存在的 task_id 返回 404。"""
        res = test_client.get("/api/v1/tasks/99999")
        assert res.status_code == 404

    def test_get_task_fields(self, test_client: TestClient):
        """TaskDetailResponse 所有字段均存在。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Fields Test"})
        task_id = res.json()["id"]

        res = test_client.get(f"/api/v1/tasks/{task_id}")
        body = res.json()

        assert "id" in body
        assert "name" in body
        assert "status" in body
        assert "progress" in body
        assert "error_message" in body
        assert "created_at" in body
        assert "updated_at" in body
        assert "documents" in body


class TestDeleteTask:
    """DELETE /api/v1/tasks/{task_id} — 删除任务。"""

    def test_delete_task_returns_204(self, test_client: TestClient):
        """删除成功返回 204 无响应体。"""
        res = test_client.post("/api/v1/tasks", json={"name": "To Delete"})
        task_id = res.json()["id"]

        res = test_client.delete(f"/api/v1/tasks/{task_id}")
        assert res.status_code == 204

    def test_delete_task_removes_record(self, test_client: TestClient):
        """删除后任务不存在（返回 404）。"""
        res = test_client.post("/api/v1/tasks", json={"name": "To Delete"})
        task_id = res.json()["id"]

        test_client.delete(f"/api/v1/tasks/{task_id}")

        res = test_client.get(f"/api/v1/tasks/{task_id}")
        assert res.status_code == 404

    def test_delete_task_removes_disk_files(self, test_client: TestClient, upload_dir: Path):
        """删除时磁盘文件一并删除。"""
        res = test_client.post("/api/v1/tasks", json={"name": "With Files"})
        task_id = res.json()["id"]

        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        test_client.post(f"/api/v1/tasks/{task_id}/documents", files=files, data=data)

        # 确认文件已写入磁盘
        task_dir = upload_dir / str(task_id)
        assert task_dir.exists()

        test_client.delete(f"/api/v1/tasks/{task_id}")

        # 目录已删除
        assert not task_dir.exists()

    def test_delete_task_removes_documents_record(self, test_client: TestClient, db_session):
        """删除时 documents 记录一并删除（无外键，由应用层控制）。"""
        res = test_client.post("/api/v1/tasks", json={"name": "With Docs"})
        task_id = res.json()["id"]

        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        test_client.post(f"/api/v1/tasks/{task_id}/documents", files=files, data=data)

        # 确认 documents 记录存在
        from app.models.models import Document
        docs = db_session.query(Document).filter(Document.task_id == task_id).all()
        assert len(docs) == 1

        test_client.delete(f"/api/v1/tasks/{task_id}")

        # documents 记录已删除
        db_session.expire_all()
        docs = db_session.query(Document).filter(Document.task_id == task_id).all()
        assert len(docs) == 0

    def test_delete_task_removes_reports_record(self, test_client: TestClient, db_session):
        """删除时 reports 记录一并删除（无外键，应用层先删 reports）。"""
        res = test_client.post("/api/v1/tasks", json={"name": "With Report"})
        task_id = res.json()["id"]

        # 手动插入 report（模拟比对完成后状态）
        from app.models.models import Report
        from app.schemas.schemas import RiskLevel
        import datetime
        report = Report(
            task_id=task_id,
            similarity_matrix={},
            risk_items=[],
            overall_risk=RiskLevel.low,
            generated_at=datetime.datetime.utcnow(),
        )
        db_session.add(report)
        db_session.commit()

        test_client.delete(f"/api/v1/tasks/{task_id}")

        # report 记录已删除
        db_session.expire_all()
        reports = db_session.query(Report).filter(Report.task_id == task_id).all()
        assert len(reports) == 0

    def test_delete_nonexistent_task(self, test_client: TestClient):
        """删除不存在的任务返回 404。"""
        res = test_client.delete("/api/v1/tasks/99999")
        assert res.status_code == 404


class TestUploadDocument:
    """POST /api/v1/tasks/{task_id}/documents — 上传投标文件。"""

    def test_upload_document_success(self, test_client: TestClient):
        """正常上传文件返回 201 和 DocumentOut。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Upload Test"})
        task_id = res.json()["id"]

        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )

        assert res.status_code == 201
        body = res.json()
        assert body["task_id"] == task_id
        assert body["supplier_name"] == "Supplier A"
        assert body["original_filename"] == "bid.txt"
        assert body["file_size"] == 7

    def test_upload_invalid_extension(self, test_client: TestClient):
        """不支持的扩展名返回 400。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Upload Test"})
        task_id = res.json()["id"]

        files = {"file": ("bid.jpg", io.BytesIO(b"content"), "image/jpeg")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )
        assert res.status_code == 400

    def test_upload_file_too_large(self, test_client: TestClient):
        """文件超过 50MB 返回 413。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Upload Test"})
        task_id = res.json()["id"]

        large_content = b"x" * (51 * 1024 * 1024)
        files = {"file": ("large.txt", io.BytesIO(large_content), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )
        assert res.status_code == 413

    def test_upload_empty_file(self, test_client: TestClient):
        """空文件返回 400。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Upload Test"})
        task_id = res.json()["id"]

        files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            f"/api/v1/tasks/{task_id}/documents",
            files=files,
            data=data,
        )
        assert res.status_code == 400

    def test_upload_to_nonexistent_task(self, test_client: TestClient):
        """上传到不存在的任务返回 404。"""
        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        res = test_client.post(
            "/api/v1/tasks/99999/documents",
            files=files,
            data=data,
        )
        assert res.status_code == 404

    def test_upload_to_completed_task(self, test_client: TestClient, db_session):
        """上传到 completed 状态任务返回 400。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Upload Test"})
        task_id = res.json()["id"]

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

    def test_upload_to_processing_task(self, test_client: TestClient, db_session):
        """上传到 processing 状态任务返回 400。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Upload Test"})
        task_id = res.json()["id"]

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


class TestRunTask:
    """POST /api/v1/tasks/{task_id}/run — 触发比对。"""

    @pytest.mark.skip(reason="Background task requires file-based database, not SQLite in-memory")
    def test_run_task_success(self, test_client: TestClient):
        """正常触发返回 202 和 RunTaskResponse。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Run Test"})
        task_id = res.json()["id"]

        # 上传 2 份文件
        for i in range(2):
            files = {"file": (f"bid_{i}.txt", io.BytesIO(b"content"), "text/plain")}
            data = {"supplier_name": f"Supplier {i}"}
            test_client.post(f"/api/v1/tasks/{task_id}/documents", files=files, data=data)

        res = test_client.post(f"/api/v1/tasks/{task_id}/run")
        assert res.status_code == 202

        body = res.json()
        assert body["message"] == "比对任务已启动"
        assert body["task_id"] == task_id

    def test_run_task_insufficient_files(self, test_client: TestClient):
        """文件数 < 2 时触发 run 返回 400。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Run Test"})
        task_id = res.json()["id"]

        # 仅上传 1 份文件
        files = {"file": ("bid.txt", io.BytesIO(b"content"), "text/plain")}
        data = {"supplier_name": "Supplier A"}
        test_client.post(f"/api/v1/tasks/{task_id}/documents", files=files, data=data)

        res = test_client.post(f"/api/v1/tasks/{task_id}/run")
        assert res.status_code == 400

    @pytest.mark.skip(reason="Background task requires file-based database, not SQLite in-memory")
    def test_run_task_processing_conflict(self, test_client: TestClient):
        """任务处于 processing 状态时重复触发 run 返回 409。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Run Test"})
        task_id = res.json()["id"]

        for i in range(2):
            files = {"file": (f"bid_{i}.txt", io.BytesIO(b"content"), "text/plain")}
            data = {"supplier_name": f"Supplier {i}"}
            test_client.post(f"/api/v1/tasks/{task_id}/documents", files=files, data=data)

        # 第一次触发
        res1 = test_client.post(f"/api/v1/tasks/{task_id}/run")
        assert res1.status_code == 202

        # 第二次触发 -> 409
        res2 = test_client.post(f"/api/v1/tasks/{task_id}/run")
        assert res2.status_code == 409

    def test_run_task_nonexistent(self, test_client: TestClient):
        """不存在的任务返回 404。"""
        res = test_client.post("/api/v1/tasks/99999/run")
        assert res.status_code == 404

    def test_run_task_zero_files(self, test_client: TestClient):
        """文件数为 0 时触发 run 返回 400。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Run Test"})
        task_id = res.json()["id"]

        res = test_client.post(f"/api/v1/tasks/{task_id}/run")
        assert res.status_code == 400

    @pytest.mark.skip(reason="Background task requires file-based database, not SQLite in-memory")
    def test_run_task_updates_status(self, test_client: TestClient):
        """触发 run 后任务状态变为 processing。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Run Test"})
        task_id = res.json()["id"]

        for i in range(2):
            files = {"file": (f"bid_{i}.txt", io.BytesIO(b"content"), "text/plain")}
            data = {"supplier_name": f"Supplier {i}"}
            test_client.post(f"/api/v1/tasks/{task_id}/documents", files=files, data=data)

        test_client.post(f"/api/v1/tasks/{task_id}/run")

        res = test_client.get(f"/api/v1/tasks/{task_id}")
        assert res.json()["status"] == "processing"
