"""
超声语音报告系统 - 患者路由
"""
from fastapi import APIRouter, HTTPException
from database import get_db
from models import PatientCreate, PatientUpdate

router = APIRouter(prefix="/api/patients", tags=["患者"])

@router.get("")
def list_patients(search: str = "", limit: int = 50):
    conn = get_db()
    if search:
        rows = conn.execute("""SELECT * FROM patients WHERE name LIKE ? OR outpatient_no LIKE ?
                                ORDER BY id DESC LIMIT ?""", (f'%{search}%', f'%{search}%', limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM patients ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"patients": [dict(r) for r in rows]}

@router.get("/{pid}")
def get_patient(pid: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404, "患者不存在")
    return {"patient": dict(row)}

@router.post("")
def create_patient(p: PatientCreate):
    conn = get_db()
    c = conn.execute("""INSERT INTO patients(name,sex,age,outpatient_no,inpatient_no,dept_name)
                        VALUES(?,?,?,?,?,?)""",
                     (p.name, p.sex, p.age, p.outpatient_no, p.inpatient_no, p.dept_name))
    conn.commit()
    row = conn.execute("SELECT * FROM patients WHERE id=?", (c.lastrowid,)).fetchone()
    conn.close()
    return {"patient": dict(row)}

@router.put("/{pid}")
def update_patient(pid: int, p: PatientUpdate):
    conn = get_db()
    fields, params = [], []
    for k in ('name','sex','age','outpatient_no','inpatient_no','dept_name'):
        v = getattr(p, k)
        if v is not None and v != '':
            fields.append(f"{k}=?")
            params.append(v)
    if fields:
        fields.append("updated_at=datetime('now','localtime')")
        params.append(pid)
        conn.execute(f"UPDATE patients SET {','.join(fields)} WHERE id=?", params)
        conn.commit()
    row = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404, "患者不存在")
    return {"patient": dict(row)}

@router.delete("/{pid}")
def delete_patient(pid: int):
    conn = get_db()
    conn.execute("DELETE FROM patients WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@router.get("/{pid}/reports")
def patient_reports(pid: int):
    conn = get_db()
    rows = conn.execute("SELECT * FROM reports WHERE patient_id=? ORDER BY created_at DESC LIMIT 50", (pid,)).fetchall()
    conn.close()
    return {"reports": [dict(r) for r in rows]}
