"""
超声语音报告系统 - 患者快捷操作路由
(从 main.py 拆出的内联路由)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db

router = APIRouter(tags=["患者"])

_VALID_STATUSES = {"待检", "检查中", "已完成", "已报告"}


class PatientAddRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    gender: str
    age: int = Field(..., ge=0, le=150)
    exam_type: str = Field(..., min_length=1, max_length=50)
    exam_part: str | None = None
    inpatient_id: str | None = None
    outpatient_id: str | None = None
    department: str | None = None
    clinical_diag: str | None = None


@router.post("/api/patients/quick-add")
async def patient_quick_add(req: PatientAddRequest):
    if not req.name.strip():
        raise HTTPException(400, "姓名不能为空")
    # 标准化性别: M/F → 男/女
    gender = {"M": "男", "F": "女"}.get(req.gender, req.gender)
    if gender not in ("男", "女"):
        raise HTTPException(400, "性别只能为 男 或 女")
    if req.age < 0 or req.age > 150:
        raise HTTPException(400, "年龄不合法(0-150)")
    if len(req.name.strip()) < 1:
        raise HTTPException(400, "姓名至少1个字符")
    if not req.exam_type.strip():
        raise HTTPException(400, "检查类型不能为空")
    if len(req.exam_type.strip()) > 50:
        raise HTTPException(400, "检查类型过长(最多50字符)")
    patient = db.patient_add(req.name.strip(), gender, req.age, req.exam_type.strip(), req.exam_part)
    db.audit_log("patient_add", patient_id=patient["id"],
                 input_text=f"{req.name},{req.gender},{req.age}",
                 output_text=f"patient_id={patient['id']}",
                 detail={"exam_type": req.exam_type})
    return {"success": True, "patient": patient}


@router.get("/api/patients/queue")
async def patient_queue():
    return {"success": True, "patients": db.patient_queue()}


@router.put("/api/patients/{patient_id}/status")
async def patient_update_status(patient_id: int, status: str = "检查中"):
    if status not in _VALID_STATUSES:
        raise HTTPException(400, f"状态值无效，可选: {_VALID_STATUSES}")
    p = db.patient_update_status(patient_id, status)
    if not p:
        raise HTTPException(404, "患者不存在")
    db.audit_log("patient_status", patient_id=patient_id,
                 input_text=status, output_text="ok")
    return {"success": True, "patient": p}
