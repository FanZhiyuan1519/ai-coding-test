from __future__ import annotations

import os
import uuid
from fastapi import UploadFile, HTTPException
from app.core.config import get_settings

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.docx'}


def save_upload_file(file: UploadFile, task_id: int) -> tuple[str, int]:
    """保存上传文件到磁盘，返回 (stored_path, file_size)"""
    settings = get_settings()
    filename = file.filename or 'unknown'
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件格式，仅支持 .txt、.pdf、.docx")
    
    content = file.file.read()
    file_size = len(content)
    
    if file_size == 0:
        raise HTTPException(status_code=400, detail="文件内容为空")
    
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(status_code=413, detail=f"文件大小超过限制（{settings.MAX_UPLOAD_SIZE_MB}MB）")
    
    stored_filename = f"{uuid.uuid4()}{ext}"
    dir_path = os.path.join(settings.UPLOAD_DIR, str(task_id))
    os.makedirs(dir_path, exist_ok=True)
    
    stored_rel_path = f"{task_id}/{stored_filename}"
    stored_full_path = os.path.join(settings.UPLOAD_DIR, stored_rel_path)
    with open(stored_full_path, 'wb') as f:
        f.write(content)
    
    return stored_rel_path, file_size
