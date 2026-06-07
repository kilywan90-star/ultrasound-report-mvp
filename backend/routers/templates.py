"""
超声语音报告系统 - 模板路由
"""
from fastapi import APIRouter
from engine import Matcher

router = APIRouter(prefix="/api/templates", tags=["模板"])

matcher: Matcher = None

def init(m: Matcher):
    global matcher
    matcher = m

@router.get("")
def list_templates(site: str = "", search: str = "", page: int = 1, size: int = 50):
    if not matcher: return {"templates": [], "total": 0}
    res = matcher.templates
    if site: res = [t for t in res if site in t.get('sites', [])]
    if search:
        res = [t for t in res if search in t.get('name','') or search in t.get('description','')]
    total = len(res)
    start = (page-1) * size
    res = res[start:start+size]
    return {"templates": res, "total": total, "page": page}

@router.get("/sites")
def list_sites():
    if not matcher: return {"sites": []}
    return {"sites": list(matcher.site_kw.keys())}
