"""检查部位枚举 API — 提供前端下拉框 + 方言识别"""

import json
from pathlib import Path
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/exam-parts", tags=["检查部位"])

CATALOG_PATH = Path(__file__).parent / "knowledge" / "exam_part_catalog.json"

_catalog = None
def _load():
    global _catalog
    if _catalog is None:
        with open(CATALOG_PATH, encoding='utf-8') as f:
            _catalog = json.load(f)
    return _catalog


@router.get("/catalog")
async def get_catalog():
    """返回完整 8 大分类 + 64 个检查部位清单"""
    cat = _load()
    return JSONResponse({
        "success": True,
        "categories": [
            {
                "id": c["id"],
                "name": c["name"],
                "exam_type": c.get("exam_type", ""),
                "parts": [{"code": p["code"], "name": p["name"]} for p in c["parts"]],
            }
            for c in cat["categories"]
        ],
        "flat_parts": cat["combined_parts"],
    })


@router.get("/dialect")
async def dialect_lookup(
    word: str = Query(..., description="方言词/口语词"),
):
    """把方言词映射回标准检查部位名"""
    cat = _load()
    matches = []
    for c in cat["categories"]:
        for p in c["parts"]:
            for d in p.get("dialect", []):
                if word in d or d in word:
                    matches.append({
                        "dialect": word,
                        "standard_name": p["name"],
                        "code": p["code"],
                        "category": c["name"],
                        "exam_type": c.get("exam_type", ""),
                    })
    return JSONResponse({
        "success": True,
        "word": word,
        "matches": matches[:5],
    })


@router.get("/search")
async def search_parts(
    q: str = Query(..., description="搜索关键词"),
):
    """模糊搜索检查部位 (支持标准名/方言)"""
    cat = _load()
    results = []
    for c in cat["categories"]:
        for p in c["parts"]:
            search_text = p["name"] + " ".join(p.get("dialect", []))
            if q in search_text:
                results.append({
                    "code": p["code"],
                    "name": p["name"],
                    "category": c["name"],
                    "exam_type": c.get("exam_type", ""),
                    "dialect": p.get("dialect", []),
                })
    return JSONResponse({
        "success": True,
        "query": q,
        "count": len(results),
        "results": results[:20],
    })
