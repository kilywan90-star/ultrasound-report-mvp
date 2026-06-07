"""
超声语音报告系统 - 固定模板/模板管理路由
(从 main.py 拆出的内联路由)
"""
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from templates import TEMPLATES
from asr_correction import correct_ASR_text
from fixed_template_engine import process_with_fixed_template, TEMPLATE_TAGS, DEFAULT_TEMPLATES

router = APIRouter(tags=["固定模板"])


class FixedTemplateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    fixed_template: str = Field(default="", max_length=5000)


@router.post("/api/fixed-template/structure")
async def fixed_template_structure(req: FixedTemplateRequest):
    """
    一键意图识别 + 字段抽取 + 填入固定模板
    - 输入: ASR文本 + 可选固定模板
    - 输出: 填充后的模板 + 意图类别 + 标签列表
    """
    if not req.text or not req.text.strip():
        raise HTTPException(400, "文本为空")
    if len(req.text) > 10000:
        raise HTTPException(400, "文本过长")

    result = process_with_fixed_template(
        correct_ASR_text(req.text),
        req.fixed_template
    )
    return {"success": True, **result}


@router.get("/api/fixed-template/tags")
async def get_template_tags():
    """获取全部模板分类标签"""
    return {"success": True, "tags": TEMPLATE_TAGS}


@router.get("/api/fixed-template/defaults")
async def get_default_templates():
    """获取各类别的默认固定模板"""
    return {"success": True, "templates": DEFAULT_TEMPLATES}


# ==================== 模板查看/编辑 API ====================


@router.get("/api/template/search")
async def search_template(q: str = "", module: str = ""):
    """搜索模板：按关键词或模块名搜索，返回匹配模板列表（含完整内容）"""
    from template_loader import load_templates, search_candidates, get_template_by_name
    templates = load_templates()
    if not templates:
        return {"success": True, "templates": []}
    if q:
        results = search_candidates(q, limit=20)
        # 补充完整内容
        for r in results:
            full = get_template_by_name(r["name"])
            if full:
                r["info1"] = full.get("info1", "")
                r["info2"] = full.get("info2", "")
        return {"success": True, "templates": results}
    if module:
        matches = [t for t in templates.values() if t.get("module") == module]
        return {"success": True, "templates": matches[:30]}
    return {"success": True, "templates": list(templates.values())[:30]}


@router.get("/api/template/{name}")
async def get_template(name: str):
    """获取单条模板的完整内容"""
    from template_loader import get_template_by_name
    tpl = get_template_by_name(name)
    if not tpl:
        raise HTTPException(404, f"模板 '{name}' 不存在")
    return {"success": True, "template": tpl}


@router.put("/api/template/{name}")
async def update_template(name: str, body: dict):
    """更新模板内容（保存到内存，重启后从CSV重新加载）"""
    from template_loader import load_templates, _template_index
    load_templates()
    if name not in _template_index:
        raise HTTPException(404, f"模板 '{name}' 不存在")
    if "info1" in body:
        _template_index[name]["info1"] = body["info1"]
    if "info2" in body:
        _template_index[name]["info2"] = body["info2"]
    logging.info(f"模板已更新: {name}")
    return {"success": True, "message": f"模板 '{name}' 已保存"}
