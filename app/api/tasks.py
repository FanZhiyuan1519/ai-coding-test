import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.models import Task, Document, Report, TaskStatus
from app.schemas.schemas import (
    TaskCreate, TaskDetailResponse, TaskListResponse, TaskListItem,
    DocumentOut, RunTaskResponse
)
from app.services.upload import save_upload_file
from app.services.background import run_compare_task

router = APIRouter()


@router.post("/tasks", response_model=TaskDetailResponse, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    task = Task(name=body.name, status=TaskStatus.pending, progress=0)
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskDetailResponse.model_validate(task)


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    total = db.query(func.count(Task.id)).scalar()
    tasks = db.query(Task).offset((page - 1) * limit).limit(limit).all()
    
    items = []
    for task in tasks:
        doc_count = db.query(func.count(Document.id)).filter(Document.task_id == task.id).scalar()
        items.append(TaskListItem(
            id=task.id,
            name=task.name,
            status=task.status,
            progress=task.progress,
            created_at=task.created_at,
            document_count=doc_count,
        ))
    
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    
    return TaskListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    documents = db.query(Document).filter(Document.task_id == task_id).all()
    
    return TaskDetailResponse(
        id=task.id,
        name=task.name,
        status=task.status,
        progress=task.progress,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
        documents=[DocumentOut.model_validate(d) for d in documents],
    )


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    from app.core.config import get_settings
    settings = get_settings()
    
    dir_path = os.path.join(settings.UPLOAD_DIR, str(task_id))
    if os.path.exists(dir_path):
        import shutil
        shutil.rmtree(dir_path)
    
    db.query(Report).filter(Report.task_id == task_id).delete()
    db.query(Document).filter(Document.task_id == task_id).delete()
    db.query(Task).filter(Task.id == task_id).delete()
    db.commit()
    
    return Response(status_code=204)


@router.post("/tasks/{task_id}/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    task_id: int,
    supplier_name: str = Form(..., min_length=1),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status in [TaskStatus.completed, TaskStatus.processing]:
        raise HTTPException(status_code=400, detail="当前状态不允许上传文件")
    
    doc_count = db.query(func.count(Document.id)).filter(Document.task_id == task_id).scalar()
    if doc_count >= 20:
        raise HTTPException(status_code=400, detail="单任务文件数已达上限（20份）")
    
    stored_path, file_size = save_upload_file(file, task_id)
    
    doc = Document(
        task_id=task_id,
        supplier_name=supplier_name,
        original_filename=file.filename or 'unknown',
        stored_path=stored_path,
        file_size=file_size,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    return DocumentOut.model_validate(doc)


@router.post("/tasks/{task_id}/run", response_model=RunTaskResponse, status_code=202)
def run_task(task_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status == TaskStatus.processing:
        raise HTTPException(status_code=409, detail="任务正在处理中，请勿重复触发")
    
    doc_count = db.query(func.count(Document.id)).filter(Document.task_id == task_id).scalar()
    if doc_count < 2:
        raise HTTPException(status_code=400, detail="至少需要上传2份投标文件才能进行比对")
    
    task.status = TaskStatus.processing
    task.progress = 0
    db.commit()
    
    background_tasks.add_task(run_compare_task, task_id)
    
    return RunTaskResponse(message="比对任务已启动", task_id=task_id)
