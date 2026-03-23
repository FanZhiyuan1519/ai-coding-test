import enum
import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum as SQLEnum
from sqlalchemy.types import TypeDecorator
from app.core.database import Base


class JSONEncodedDict(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value


class TaskStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class RiskLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    status = Column(SQLEnum(TaskStatus), nullable=False, default=TaskStatus.pending)
    progress = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    supplier_name = Column(String(255), nullable=False)
    original_filename = Column(String(512), nullable=False)
    stored_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=True)
    extracted_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, unique=True, index=True)
    similarity_matrix = Column(JSONEncodedDict, nullable=True)
    risk_items = Column(JSONEncodedDict, nullable=True)
    overall_risk = Column(SQLEnum(RiskLevel), nullable=True)
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
