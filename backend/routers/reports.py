"""
超声语音报告系统 - 报告路由 (v3.0 全量数据版)
"""
import json, uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db
from models import ReportCreate, ReportUpdate

router = APIRouter(prefix="/api/reports", tags=["报告"])

REPORT_FIELDS = [
    'id','doctor','doctor_id','patient_id','patient_name','patient_sex','patient_age',
    'template_id','template_name','description','diagnosis',
    'audio_file','asr_raw_text','asr_corrected_text','asr_source','asr_quality',
    'intent_sites','intent_findings','intent_is_normal',
    'match_score','matched_sites','match_candidates','variables',
    'status','created_at','updated_at','confirmed_at',
    'his_report_id','external_ref'
]

@router.get("")
def list_reports(
    status: str = "", doctor: str = "", patient_id: int = 0,
    template_name: str = "", date_from: str = "", date_to: str = "",
    limit: int = 100, offset: int = 0
):
    conn = get_db()
    sql = "SELECT * FROM reports WHERE 1=1"
    params = []
    if status: sql += " AND status=?"; params.append(status)
    if doctor: sql += " AND doctor=?"; params.append(doctor)
    if patient_id: sql += " AND patient_id=?"; params.append(patient_id)
    if template_name: sql += " AND template_name LIKE ?"; params.append(f'%{template_name}%')
    if date_from: sql += " AND date(created_at) >= ?"; params.append(date_from)
    if date_to: sql += " AND date(created_at) <= ?"; params.append(date_to)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"; params.append(limit); params.append(offset)
    total = conn.execute("SELECT COUNT(*) as n FROM reports").fetchone()['n']
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return {"reports": [dict(r) for r in rows], "total": total}

@router.get("/{rid}")
def get_report(rid: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    if not row: conn.close(); raise HTTPException(404, "报告不存在")
    edits = conn.execute("SELECT * FROM report_edits WHERE report_id=? ORDER BY id", (rid,)).fetchall()
    # 关联的录音
    recordings = conn.execute("SELECT * FROM audio_recordings WHERE report_id=? ORDER BY created_at DESC", (rid,)).fetchall()
    asr_logs = conn.execute("SELECT * FROM asr_logs WHERE report_id=? ORDER BY created_at DESC", (rid,)).fetchall()
    conn.close()
    return {
        "report": dict(row), "edits": [dict(e) for e in edits],
        "recordings": [dict(r) for r in recordings],
        "asr_logs": [dict(l) for l in asr_logs],
    }

@router.post("")
def create_report(r: ReportCreate):
    rid = "RPT-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()
    conn = get_db()
    conn.execute("""INSERT INTO reports(id,doctor,patient_id,patient_name,patient_sex,patient_age,
                    voice_text,template_id,template_name,description,diagnosis,
                    match_score,matched_sites,variables,asr_raw_text,asr_corrected_text,asr_source,asr_quality)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (rid, r.doctor, r.patient_id, r.patient_name, r.patient_sex, r.patient_age,
                  r.voice_text, r.template_id, r.template_name,
                  r.description, r.diagnosis, r.match_score, r.matched_sites, r.variables,
                  r.asr_raw_text or '', r.asr_corrected_text or '', r.asr_source or '', r.asr_quality or 0))
    conn.commit()
    row = conn.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    conn.close()
    return {"report": dict(row)}

@router.put("/{rid}")
def update_report(rid: str, r: ReportUpdate):
    conn = get_db()
    fields, params = [], []
    for k in ('description','diagnosis','status','patient_name','patient_sex','his_report_id','external_ref'):
        v = getattr(r, k)
        if v is not None:
            fields.append(f"{k}=?")
            params.append(v)
    if r.patient_age is not None:
        fields.append("patient_age=?")
        params.append(r.patient_age)
    if r.status == "confirmed":
        fields.append("confirmed_at=datetime('now','localtime')")
    fields.append("updated_at=datetime('now','localtime')")
    params.append(rid)
    conn.execute(f"UPDATE reports SET {','.join(fields)} WHERE id=?", params)
    conn.commit()
    row = conn.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404, "报告不存在")
    return {"report": dict(row)}

@router.delete("/{rid}")
def delete_report(rid: str):
    conn = get_db()
    conn.execute("DELETE FROM reports WHERE id=?", (rid,))
    conn.execute("DELETE FROM report_edits WHERE report_id=?", (rid,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

# ===== 数据分析API =====
@router.get("/analysis/daily")
def daily_report_count(days: int = 30):
    """每日报告量统计"""
    conn = get_db()
    rows = conn.execute("""
        SELECT date(created_at) as day, COUNT(*) as cnt,
               SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) as confirmed_cnt
        FROM reports
        WHERE created_at >= datetime('now', ? || ' days')
        GROUP BY date(created_at) ORDER BY day
    """, (f'-{days}',)).fetchall()
    conn.close()
    return {"daily": [dict(r) for r in rows]}

@router.get("/analysis/doctors")
def doctor_report_stats():
    """医生工作量统计"""
    conn = get_db()
    rows = conn.execute("""
        SELECT doctor, COUNT(*) as total, SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) as confirmed,
               AVG(match_score) as avg_score, MAX(created_at) as last_active
        FROM reports GROUP BY doctor ORDER BY total DESC
    """).fetchall()
    conn.close()
    return {"doctors": [dict(r) for r in rows]}

@router.get("/analysis/templates")
def template_usage_stats():
    """模板使用统计"""
    conn = get_db()
    rows = conn.execute("""
        SELECT template_name, COUNT(*) as cnt, AVG(match_score) as avg_score
        FROM reports WHERE template_name != '' GROUP BY template_name ORDER BY cnt DESC LIMIT 50
    """).fetchall()
    conn.close()
    return {"templates": [dict(r) for r in rows]}

@router.get("/export")
def export_reports(format: str = "json", date_from: str = "", date_to: str = "", limit: int = 1000):
    """数据导出供外部系统调阅"""
    conn = get_db()
    sql = "SELECT * FROM reports WHERE 1=1"
    params = []
    if date_from: sql += " AND date(created_at) >= ?"; params.append(date_from)
    if date_to: sql += " AND date(created_at) <= ?"; params.append(date_to)
    sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    reports = [dict(r) for r in rows]
    if format == "csv":
        import csv, io
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow(REPORT_FIELDS)
        for r in reports:
            w.writerow([r.get(f, '') for f in REPORT_FIELDS])
        return {"csv": output.getvalue(), "count": len(reports)}
    return {"reports": reports, "count": len(reports)}
