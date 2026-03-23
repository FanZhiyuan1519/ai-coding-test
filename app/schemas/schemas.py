from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class RiskLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class DocumentOut(BaseModel):
    id: int
    task_id: int
    supplier_name: str
    original_filename: str
    stored_path: str
    file_size: Optional[int] = None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class TaskListItem(BaseModel):
    id: int
    name: str
    status: TaskStatus
    progress: int
    created_at: datetime
    document_count: int

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    items: List[TaskListItem]
    total: int
    page: int
    limit: int
    total_pages: int


class TaskDetailResponse(BaseModel):
    id: int
    name: str
    status: TaskStatus
    progress: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentOut] = []

    model_config = ConfigDict(from_attributes=True)


class RiskDetail(BaseModel):
    key_info_match: List[str]
    similarity_ratio: float
    lcs_length: int
    price_correlation: Optional[float] = None
    price_values: Dict[str, Optional[float]] = {}


class RiskItem(BaseModel):
    supplier_a: str
    supplier_b: str
    level: RiskLevel
    reason: str
    detail: RiskDetail


class ReportOut(BaseModel):
    id: int
    task_id: int
    similarity_matrix: Optional[Dict[str, Dict[str, float]]] = None
    risk_items: Optional[List[RiskItem]] = None
    overall_risk: Optional[RiskLevel] = None
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunTaskResponse(BaseModel):
    message: str
    task_id: int
