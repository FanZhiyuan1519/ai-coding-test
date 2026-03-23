from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Report
from app.schemas.schemas import ReportOut, RiskItem, RiskDetail, RiskLevel

router = APIRouter()


@router.get("/reports/task/{task_id}", response_model=ReportOut)
def get_report(task_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.task_id == task_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在，请先完成比对任务")
    
    risk_items = None
    if report.risk_items is not None:
        risk_items = [RiskItem(
            supplier_a=item['supplier_a'],
            supplier_b=item['supplier_b'],
            level=RiskLevel(item['level']),
            reason=item['reason'],
            detail=RiskDetail(**item['detail']),
        ) for item in report.risk_items]
    
    return ReportOut(
        id=report.id,
        task_id=report.task_id,
        similarity_matrix=report.similarity_matrix,
        risk_items=risk_items,
        overall_risk=report.overall_risk,
        generated_at=report.generated_at,
    )
