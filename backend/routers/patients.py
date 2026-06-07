"""
超声语音报告系统 - 患者路由（兼容 db.py + database.py 双schema）
"""
from fastapi import APIRouter, HTTPException
from database import get_db
from models import PatientCreate, PatientUpdate

router = APIRouter(prefix="/api/patients", tags=["患者"])


@router.get("")
def list_patients(search: str = "", limit: int = 50):
    conn = get_db()
    if search:
        try:
            # db.py schema: name + outpatient_id
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
