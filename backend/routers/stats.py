"""
超声语音报告系统 - 统计路由
"""
from fastapi import APIRouter
from database import get_db

router = APIRouter(prefix="/api/stats", tags=["统计"])

@router.get("")
def get_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as n FROM reports").fetchone()['n']
    confirmed = conn.execute("SELECT COUNT(*) as n FROM reports WHERE status='confirmed'").fetchone()['n']
    draft = conn.execute("SELECT COUNT(*) as n FROM reports WHERE status='draft'").fetchone()['n']
    today = conn.execute("""SELECT COUNT(*) as n FROM reports
                            WHERE date(created_at)=date('now','localtime')""").fetchone()['n']
    try:
        match_count = conn.execute("SELECT COUNT(*) as n FROM match_log").fetchone()['n']
    except Exception:
        match_count = 0
    doc_count = conn.execute("SELECT COUNT(*) as n FROM doctors").fetchone()['n']
    patient_count = conn.execute("SELECT COUNT(*) as n FROM patients").fetchone()['n']

    top_doctors = conn.execute("""SELECT doctor,COUNT(*) as cnt FROM reports
                                   GROUP BY doctor ORDER BY cnt DESC LIMIT 10""").fetchall()
    top_templates = conn.execute("""SELECT template_name,COUNT(*) as cnt FROM reports
                                     WHERE template_name!='' GROUP BY template_name
                                     ORDER BY cnt DESC LIMIT 10""").fetchall()
    status_dist = conn.execute("""SELECT status,COUNT(*) as cnt FROM reports
                                   GROUP BY status ORDER BY cnt DESC""").fetchall()

    # 今日各医生
    today_doctors = conn.execute("""SELECT doctor,COUNT(*) as cnt FROM reports
                                     WHERE date(created_at)=date('now','localtime')
                                     GROUP BY doctor ORDER BY cnt DESC LIMIT 10""").fetchall()

    conn.close()
    return {
        "total_reports": total, "confirmed": confirmed, "draft": draft,
        "today_reports": today, "total_matches": match_count,
        "total_doctors": doc_count, "total_patients": patient_count,
        "top_doctors": [dict(r) for r in top_doctors],
        "top_templates": [dict(r) for r in top_templates],
        "status_dist": [dict(r) for r in status_dist],
        "today_doctors": [dict(r) for r in today_doctors],
    }
