"""
超声语音报告系统 - 患者路由（完整版：CRUD + 快捷入队 + 队列管理）
合并自 patients.py(v3 database.py schema) + quick_patients.py(db.py schema)
统一使用 database.py 数据层
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from models import PatientCreate, PatientUpdate

router = APIRouter(prefix="/api/patients", tags=["患者"])

_VALID_STATUSES = {"待检", "检查中", "已完成", "已报告"}


# ===== 快捷入队（原 quick_patients.py） =====

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


@router.post("/quick-add")
async def patient_quick_add(req: PatientAddRequest):
    """快捷入队（一次录入所有字段）"""
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

    conn = get_db()
    try:
        c = conn.execute(
            """INSERT INTO patients(name, gender, age, exam_type, exam_part,
               outpatient_id, inpatient_id, department, clinical_diag, status)
               VALUES(?,?,?,?,?,?,?,?,?,'待检')""",
            (req.name.strip(), gender, req.age, req.exam_type.strip(),
             req.exam_part, req.outpatient_id, req.inpatient_id,
             req.department, req.clinical_diag)
        )
        conn.commit()
        pid = c.lastrowid
        row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
        patient = dict(row)
    except Exception as e:
        conn.close()
        raise HTTPException(400, f"创建失败: {e}")
    conn.close()
    return {"success": True, "patient": patient}


@router.get("/queue")
async def patient_queue():
    """获取排队列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM patients WHERE status IN ('待检','检查中') ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return {"success": True, "patients": [dict(r) for r in rows]}


@router.put("/{patient_id}/status")
async def patient_update_status(patient_id: int, status: str = "检查中"):
    """更新患者状态"""
    if status not in _VALID_STATUSES:
        raise HTTPException(400, f"状态值无效，可选: {_VALID_STATUSES}")
    conn = get_db()
    conn.execute("UPDATE patients SET status=? WHERE id=?", (status, patient_id))
    conn.commit()
    row = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "患者不存在")
    return {"success": True, "patient": dict(row)}


# ===== 标准 CRUD（原 patients.py） =====

@router.get("")
def list_patients(search: str = "", limit: int = 50):
    conn = get_db()
    if search:
        try:
            rows = conn.execute(
                "SELECT * FROM patients WHERE name LIKE ? OR outpatient_id LIKE ? ORDER BY id DESC LIMIT ?",
                (f'%{search}%', f'%{search}%', limit)
            ).fetchall()
        except Exception:
            rows = conn.execute(
                "SELECT * FROM patients WHERE name LIKE ? ORDER BY id DESC LIMIT ?",
                (f'%{search}%', limit)
            ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM patients ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"patients": [dict(r) for r in rows]}


@router.get("/{pid}")
def get_patient(pid: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "患者不存在")
    return {"patient": dict(row)}


@router.post("")
def create_patient(p: PatientCreate):
    conn = get_db()
    try:
        c = conn.execute(
            "INSERT INTO patients(name,sex,age,outpatient_no,dept_name) VALUES(?,?,?,?,?)",
            (p.name, p.sex, p.age, p.outpatient_no, p.dept_name)
        )
        conn.commit()
        pid = c.lastrowid
        row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
        conn.close()
        return {"patient": dict(row)}
    except Exception as e:
        conn.close()
        raise HTTPException(400, f"创建失败: {e}")


@router.put("/{pid}")
def update_patient(pid: int, p: PatientUpdate):
    conn = get_db()
    sets = []
    vals = []
    for field in ['name', 'sex', 'age', 'outpatient_no', 'dept_name']:
        v = getattr(p, field, None)
        if v is not None:
            sets.append(f"{field}=?")
            vals.append(v)
    if not sets:
        conn.close()
        raise HTTPException(400, "无更新字段")
    vals.append(pid)
    conn.execute(f"UPDATE patients SET {','.join(sets)} WHERE id=?", vals)
    conn.commit()
    row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "患者不存在")
    return {"patient": dict(row)}


@router.delete("/{pid}")
def delete_patient(pid: int):
    conn = get_db()
    conn.execute("DELETE FROM patients WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return {"success": True}
