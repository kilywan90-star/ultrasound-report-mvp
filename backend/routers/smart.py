"""
超声报告实时智能匹配 - API路由
/v2/smart/match   实时增量匹配
/v2/smart/status  匹配引擎状态
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/v2/smart", tags=["智能匹配"])


class SmartMatchQuery(BaseModel):
    text: str
    doctor: str = ""


@router.post("/match")
def smart_match(q: SmartMatchQuery):
    """实时增量匹配，返回Top5+自动触发状态"""
    if not q.text.strip():
        raise HTTPException(400, "输入为空")

    try:
        from smart_matcher import get_matcher
        matcher = get_matcher()
        if not matcher:
            raise HTTPException(503, "匹配引擎未就绪")
        result = matcher.match(q.text)
        return result
    except Exception as e:
        raise HTTPException(500, f"匹配失败: {str(e)}")


@router.post("/full")
def smart_full(q: SmartMatchQuery):
    """完整管线：匹配+填充"""
    if not q.text.strip():
        raise HTTPException(400, "输入为空")

    try:
        from smart_matcher import get_matcher
        matcher = get_matcher()
        if not matcher:
            raise HTTPException(503, "匹配引擎未就绪")
        result = matcher.match(q.text)
        return result
    except Exception as e:
        raise HTTPException(500, f"失败: {str(e)}")


@router.get("/status")
def smart_status():
    """智能匹配引擎状态"""
    from smart_matcher import get_matcher
    matcher = get_matcher()
    if matcher:
        return {
            "status": "ready",
            "records": len(matcher.records),
            "keywords": len(matcher.inverted_index),
        }
    return {"status": "loading", "records": 0, "keywords": 0}
