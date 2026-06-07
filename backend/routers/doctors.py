"""
超声语音报告系统 - 医生路由
"""
from fastapi import APIRouter, HTTPException
from database import get_db
from models import DoctorCreate

router = APIRouter(prefix="/api/doctors", tags=["医生"])

@router.get("")
def list_doctors():
    conn = get_db()
    rows = conn.execute("SELECT * FROM doctors ORDER BY name").fetchall()
    conn.close()
    return {"doctors": [dict(r) for r in rows]}

@router.post("")
def create_doctor(d: DoctorCreate):
    conn = get_db()
    try:
        c = conn.execute("INSERT INTO doctors (name,department,title) VALUES (?,?,?)",
                        (d.name, d.department, d.title))
        conn.commit()
        row = conn.execute("SELECT * FROM doctors WHERE id=?", (c.lastrowid,)).fetchone()
        conn.close()
        return {"doctor": dict(row)}
    except:
        conn.close()
        raise HTTPException(400, "医生已存在")

@router.put("/{did}")
def update_doctor(did: int, d: DoctorCreate):
    conn = get_db()
    conn.execute("UPDATE doctors SET name=?,department=?,title=?,updated_at=datetime('now','localtime') WHERE id=?",
                (d.name, d.department, d.title, did))
    conn.commit()
    row = conn.execute("SELECT * FROM doctors WHERE id=?", (did,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404, "医生不存在")
    return {"doctor": dict(row)}

@router.delete("/{did}")
def delete_doctor(did: int):
    conn = get_db()
    conn.execute("DELETE FROM doctors WHERE id=?", (did,))
    conn.commit()
    conn.close()
    return {"status": "ok"}
