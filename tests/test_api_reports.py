"""
/api/v1/reports 路由测试套件。

覆盖场景：
- GET /reports/task/{id}: 任务完成后返回完整报告、similarity_matrix 结构正确、risk_items 只含 medium/high、overall_risk 正确
- GET /reports/task/{id}: 任务未完成返回 404
"""
import datetime
import pytest
from fastapi.testclient import TestClient

from app.models.models import Document, Report, Task
from app.schemas.schemas import RiskLevel


class TestGetReport:
    """GET /api/v1/reports/task/{task_id} — 获取比对报告。"""

    def test_get_report_not_found(self, test_client: TestClient):
        """任务未完成（无报告）时返回 404。"""
        res = test_client.post("/api/v1/tasks", json={"name": "No Report"})
        task_id = res.json()["id"]

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        assert res.status_code == 404

    def test_get_report_nonexistent_task(self, test_client: TestClient):
        """不存在的任务返回 404。"""
        res = test_client.get("/api/v1/reports/task/99999")
        assert res.status_code == 404

    def test_get_report_success(self, test_client: TestClient, db_session):
        """任务完成后返回完整报告。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Report Test"})
        task_id = res.json()["id"]

        # 插入报告记录
        report = Report(
            task_id=task_id,
            similarity_matrix={
                "供应商A": {"供应商B": 78.5, "供应商C": 12.3},
                "供应商B": {"供应商A": 78.5, "供应商C": 15.0},
                "供应商C": {"供应商A": 12.3, "供应商B": 15.0},
            },
            risk_items=[
                {
                    "supplier_a": "供应商A",
                    "supplier_b": "供应商B",
                    "level": "high",
                    "reason": "经营地址完全一致；文件雷同比例78.5%，最长连续相同段落215字，高度疑似围标。",
                    "detail": {
                        "key_info_match": ["经营地址", "联系电话"],
                        "similarity_ratio": 78.5,
                        "lcs_length": 215,
                        "price_correlation": 0.997,
                        "price_values": {"供应商A": 1052000.0, "供应商B": 925000.0},
                    },
                }
            ],
            overall_risk=RiskLevel.high,
            generated_at=datetime.datetime.utcnow(),
        )
        db_session.add(report)
        db_session.commit()

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        assert res.status_code == 200

        body = res.json()
        assert body["task_id"] == task_id
        assert body["overall_risk"] == "high"
        assert body["similarity_matrix"] is not None
        assert body["risk_items"] is not None
        assert body["generated_at"] is not None

    def test_similarity_matrix_structure(self, test_client: TestClient, db_session):
        """similarity_matrix 为嵌套 dict，float 值保留 1 位小数。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Matrix Test"})
        task_id = res.json()["id"]

        matrix = {
            "A": {"B": 78.5, "C": 12.3},
            "B": {"A": 78.5, "C": 15.0},
            "C": {"A": 12.3, "B": 15.0},
        }
        report = Report(
            task_id=task_id,
            similarity_matrix=matrix,
            risk_items=[],
            overall_risk=RiskLevel.low,
            generated_at=datetime.datetime.utcnow(),
        )
        db_session.add(report)
        db_session.commit()

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        body = res.json()

        matrix = body["similarity_matrix"]
        assert "A" in matrix
        assert "B" in matrix["A"]
        assert matrix["A"]["B"] == 78.5
        # float 保留 1 位小数
        assert isinstance(matrix["A"]["B"], float)

    def test_risk_items_only_medium_and_high(self, test_client: TestClient, db_session):
        """
        risk_items 只含 medium 和 high 等级，low 不写入报告。
        本测试验证报告结构正确（low 不出现）。
        """
        res = test_client.post("/api/v1/tasks", json={"name": "Risk Items Test"})
        task_id = res.json()["id"]

        report = Report(
            task_id=task_id,
            similarity_matrix={},
            risk_items=[
                {
                    "supplier_a": "A",
                    "supplier_b": "B",
                    "level": "high",
                    "reason": "reason text",
                    "detail": {
                        "key_info_match": [],
                        "similarity_ratio": 80.0,
                        "lcs_length": 200,
                        "price_correlation": None,
                        "price_values": {},
                    },
                },
                {
                    "supplier_a": "A",
                    "supplier_b": "C",
                    "level": "medium",
                    "reason": "reason text",
                    "detail": {
                        "key_info_match": [],
                        "similarity_ratio": 30.0,
                        "lcs_length": 50,
                        "price_correlation": None,
                        "price_values": {},
                    },
                },
            ],
            overall_risk=RiskLevel.high,
            generated_at=datetime.datetime.utcnow(),
        )
        db_session.add(report)
        db_session.commit()

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        body = res.json()

        levels = [item["level"] for item in body["risk_items"]]
        assert "high" in levels
        assert "medium" in levels
        assert "low" not in levels

    def test_overall_risk_highest_level(self, test_client: TestClient, db_session):
        """overall_risk 为所有文件对中的最高等级。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Overall Risk Test"})
        task_id = res.json()["id"]

        # risk_items 全为 medium，overall_risk 应为 medium
        report = Report(
            task_id=task_id,
            similarity_matrix={},
            risk_items=[
                {
                    "supplier_a": "A",
                    "supplier_b": "B",
                    "level": "medium",
                    "reason": "reason",
                    "detail": {
                        "key_info_match": [],
                        "similarity_ratio": 30.0,
                        "lcs_length": 50,
                        "price_correlation": None,
                        "price_values": {},
                    },
                }
            ],
            overall_risk=RiskLevel.medium,
            generated_at=datetime.datetime.utcnow(),
        )
        db_session.add(report)
        db_session.commit()

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        body = res.json()
        assert body["overall_risk"] == "medium"

    def test_report_response_fields(self, test_client: TestClient, db_session):
        """ReportOut 所有字段均存在且类型正确。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Fields Test"})
        task_id = res.json()["id"]

        report = Report(
            task_id=task_id,
            similarity_matrix={},
            risk_items=[],
            overall_risk=RiskLevel.low,
            generated_at=datetime.datetime.utcnow(),
        )
        db_session.add(report)
        db_session.commit()

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        body = res.json()

        assert "id" in body
        assert "task_id" in body
        assert "similarity_matrix" in body
        assert "risk_items" in body
        assert "overall_risk" in body
        assert "generated_at" in body

    def test_report_task_not_completed(self, test_client: TestClient):
        """任务处于 pending 或 processing 状态时，报告不存在返回 404。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Pending Task"})
        task_id = res.json()["id"]

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        assert res.status_code == 404

    def test_risk_item_detail_structure(self, test_client: TestClient, db_session):
        """risk_item.detail 包含所有必需字段。"""
        res = test_client.post("/api/v1/tasks", json={"name": "Detail Test"})
        task_id = res.json()["id"]

        report = Report(
            task_id=task_id,
            similarity_matrix={},
            risk_items=[
                {
                    "supplier_a": "A",
                    "supplier_b": "B",
                    "level": "high",
                    "reason": "reason text",
                    "detail": {
                        "key_info_match": ["经营地址"],
                        "similarity_ratio": 78.5,
                        "lcs_length": 215,
                        "price_correlation": 0.997,
                        "price_values": {"A": 1052000.0, "B": 925000.0},
                    },
                }
            ],
            overall_risk=RiskLevel.high,
            generated_at=datetime.datetime.utcnow(),
        )
        db_session.add(report)
        db_session.commit()

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        body = res.json()

        item = body["risk_items"][0]
        detail = item["detail"]

        assert "key_info_match" in detail
        assert isinstance(detail["key_info_match"], list)
        assert "similarity_ratio" in detail
        assert isinstance(detail["similarity_ratio"], float)
        assert "lcs_length" in detail
        assert isinstance(detail["lcs_length"], int)
        assert "price_correlation" in detail
        assert "price_values" in detail
        assert isinstance(detail["price_values"], dict)

    def test_empty_risk_items(self, test_client: TestClient, db_session):
        """无风险项时 risk_items 为空列表。"""
        res = test_client.post("/api/v1/tasks", json={"name": "No Risk"})
        task_id = res.json()["id"]

        report = Report(
            task_id=task_id,
            similarity_matrix={"A": {"B": 10.0}, "B": {"A": 10.0}},
            risk_items=[],
            overall_risk=RiskLevel.low,
            generated_at=datetime.datetime.utcnow(),
        )
        db_session.add(report)
        db_session.commit()

        res = test_client.get(f"/api/v1/reports/task/{task_id}")
        body = res.json()
        assert body["risk_items"] == []
        assert body["overall_risk"] == "low"
