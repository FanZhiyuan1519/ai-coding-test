import logging
from datetime import datetime
from app.core.database import SessionLocal
from app.models.models import Task, Document, Report, TaskStatus, RiskLevel
from app.services.extract import extract_text
from app.services.compare import (
    extract_key_info_regex, check_key_info, check_similarity, check_price, assess_risk
)
from app.services.ai import extract_key_info_ai, generate_risk_reason

logger = logging.getLogger(__name__)


def run_compare_task(task_id: int):
    """后台比对任务"""
    db = SessionLocal()
    try:
        _execute(task_id, db)
    except Exception as e:
        logger.error(f"比对任务失败 {task_id}: {e}")
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.failed
            task.error_message = str(e)
            task.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _execute(task_id: int, db):
    """执行比对主流程"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return
    
    task.progress = 10
    db.commit()
    
    documents = db.query(Document).filter(Document.task_id == task_id).all()
    
    for i, doc in enumerate(documents):
        try:
            if not doc.extracted_text:
                doc.extracted_text = extract_text(doc.stored_path)
                db.commit()
        except Exception as e:
            logger.warning(f"提取文档 {doc.id} 失败: {e}")
            doc.extracted_text = ""
            db.commit()
        
        task.progress = 10 + int((i + 1) / len(documents) * 50)
        db.commit()
    
    valid_docs = [d for d in documents if d.extracted_text and len(d.extracted_text.strip()) >= 100]
    if len(valid_docs) < 2:
        task.status = TaskStatus.failed
        task.error_message = "有效文件不足2份，无法进行比对"
        db.commit()
        return
    
    task.progress = 60
    db.commit()
    
    key_infos = {}
    for doc in valid_docs:
        info = extract_key_info_regex(doc.extracted_text)
        non_none = sum(1 for v in info.values() if v is not None)
        if non_none < 3:
            info_ai = extract_key_info_ai(doc.extracted_text)
            for k, v in info_ai.items():
                if info[k] is None and v is not None:
                    info[k] = v
        key_infos[doc.id] = info
    
    similarity_matrix = {}
    risk_items = []
    
    for i, doc_a in enumerate(valid_docs):
        similarity_matrix[doc_a.supplier_name] = {}
        for doc_b in valid_docs:
            if doc_a.id == doc_b.id:
                continue
            
            text_a = doc_a.extracted_text
            text_b = doc_b.extracted_text
            
            info_match = check_key_info(key_infos[doc_a.id], key_infos[doc_b.id])
            similarity_ratio, lcs_length = check_similarity(text_a, text_b)
            price_correlation, price_values = check_price(text_a, text_b)
            
            level = assess_risk(info_match, similarity_ratio, lcs_length, price_correlation)
            
            similarity_matrix[doc_a.supplier_name][doc_b.supplier_name] = similarity_ratio
            
            if level in [RiskLevel.high, RiskLevel.medium]:
                reason = generate_risk_reason(
                    doc_a.supplier_name, doc_b.supplier_name, level,
                    {
                        'key_info_match': info_match,
                        'similarity_ratio': similarity_ratio,
                        'lcs_length': lcs_length,
                        'price_correlation': price_correlation,
                        'price_values': price_values,
                    }
                )
                
                risk_items.append({
                    'supplier_a': doc_a.supplier_name,
                    'supplier_b': doc_b.supplier_name,
                    'level': level.value,
                    'reason': reason,
                    'detail': {
                        'key_info_match': info_match,
                        'similarity_ratio': similarity_ratio,
                        'lcs_length': lcs_length,
                        'price_correlation': price_correlation,
                        'price_values': price_values,
                    }
                })
    
    task.progress = 75
    db.commit()
    
    overall_risk = RiskLevel.low
    for item in risk_items:
        if item['level'] == RiskLevel.high.value:
            overall_risk = RiskLevel.high
            break
        elif item['level'] == RiskLevel.medium.value:
            overall_risk = RiskLevel.medium
    
    existing_report = db.query(Report).filter(Report.task_id == task_id).first()
    if existing_report:
        db.delete(existing_report)
    
    report = Report(
        task_id=task_id,
        similarity_matrix=json.dumps(similarity_matrix),
        risk_items=json.dumps(risk_items),
        overall_risk=overall_risk,
    )
    db.add(report)
    
    task.progress = 100
    task.status = TaskStatus.completed
    task.updated_at = datetime.utcnow()
    db.commit()
