"""
超声语音报告系统 - 匹配路由
"""
import re
from fastapi import APIRouter
from database import get_db
from engine import Matcher
from models import MatchQuery

router = APIRouter(prefix="/api/match", tags=["匹配"])

matcher: Matcher = None

def init(m: Matcher):
    global matcher
    matcher = m

@router.post("")
def match_text(q: MatchQuery):
    if not matcher: return {"matches": [], "sites": []}
    if not q.text.strip(): return {"matches": [], "sites": []}

    matches = matcher.match(q.text)
    sites = list(matcher.sites(re.sub(r'\s+', '', q.text)))
    variables = matcher.extract_variables(q.text)

    conn = get_db()
    conn.execute("""INSERT INTO match_log(voice_text,best_template_id,best_template_name,
                    best_score,matched_sites,result_count,doctor)
                    VALUES(?,?,?,?,?,?,?)""",
                 (q.text[:200], matches[0]['template_id'] if matches else '',
                  matches[0]['template_name'] if matches else '',
                  matches[0]['score'] if matches else 0,
                  ','.join(sites), len(matches), q.doctor))
    conn.commit()
    conn.close()

    return {"matches": matches, "sites": sites, "variables": variables}
