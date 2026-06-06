#!/usr/bin/env python3
"""
API endpoint: GET /api/section-templates
返回 33 张精选段落模板 + 变量定义, 供前端模板选择器使用
"""
import json, csv, re, time, logging
from pathlib import Path
from collections import defaultdict, Counter
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/section-templates", tags=["section-templates"])

HERE = Path(__file__).parent
TPL_FILE = HERE / "knowledge" / "section_templates_merged.json"
RULES_FILE = HERE / "knowledge" / "matching_rules_merged.json"

_templates_cache = None
_rules_cache = None

def _load():
    global _templates_cache, _rules_cache
    if _templates_cache is not None:
        return _templates_cache, _rules_cache
    with open(TPL_FILE, encoding='utf-8') as f:
        _templates_cache = json.load(f)
    with open(RULES_FILE, encoding='utf-8') as f:
        _rules_cache = json.load(f)
    return _templates_cache, _rules_cache


@router.get("/list")
async def list_templates(
    category: str = Query(None, description="Filter by category")
):
    """
    返回所有段落模板列表. 按 category 分组.
    包含: template_id, text (原始含变量标记), variables (变量定义), frequency, category
    """
    tpl, rules = _load()

    by_cat = defaultdict(list)
    for tid, info in tpl.items():
        cat = info.get('category', '其他')
        if category and cat != category:
            continue
        freq = info.get('frequency_after_merge', info.get('frequency', 0))
        merged_count = info.get('merged_count', 1)
        entry = {
            "id": tid,
            "text": info['text'],
            "category": cat,
            "frequency": freq,
            "merged_count": merged_count,
        }
        if 'variables' in info:
            entry['variables'] = info['variables']
        if 'merged_ids' in info:
            entry['merged_ids'] = info['merged_ids']
        if tid in rules:
            entry['keywords'] = rules[tid].get('keywords', [])
        by_cat[cat].append(entry)

    # Sort within each category by frequency desc
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: -x['frequency'])

    return JSONResponse({
        "success": True,
        "total": len(tpl),
        "categories": {
            cat: {
                "count": len(items),
                "templates": items,
            }
            for cat, items in sorted(by_cat.items(), key=lambda x: -sum(i['frequency'] for i in x[1]))
        },
    })


@router.get("/match")
async def match_template(
    text: str = Query(..., description="ASR 文本或自由文本"),
    category: str = Query(None, description="Optional exam category filter"),
):
    """
    对输入文本做模板匹配, 返回 top-5 最佳模板.
    使用 4-gram Jaccard 相似度算法.
    """
    tpl, rules = _load()

    def strip_all(t):
        t = re.sub(r'\s+', '', t); t = re.sub(r'[，,。；;：:！!、]', '', t)
        t = re.sub(r'\[[^\]]*\]', '', t); return t
    def norm_num(t):
        t = re.sub(r'\d+\.?\d*\s*[xX×]\s*\d+\.?\d*\s*(?:[xX×]\s*\d+\.?\d*)?', '#x#', t)
        t = re.sub(r'\d+\.?\d+\s*mm', '#mm', t); t = re.sub(r'\d+\.?\d+\s*cm', '#cm', t)
        t = re.sub(r'\d+\.?\d+\s*%', '#%', t); t = re.sub(r'\d+\.?\d+', '#', t)
        return t

    # Build 4-gram index (cached)
    gram_index = defaultdict(list)
    tpl_sigs = {}
    for tid, info in tpl.items():
        if category and info.get('category', '') != category:
            continue
        variants = [info['text']]
        for vd in info.get('variables', []):
            new_v = []
            for v in variants:
                m = re.search(r'\[([^\]]*)\]', v)
                if not m: new_v.append(v); continue
                for p in m.group(1).split(';'):
                    new_v.append(v[:m.start()] + (p or '') + v[m.end():])
            variants = new_v
        sigs = set()
        for v in variants:
            sigs.add(strip_all(norm_num(v)))
        tpl_sigs[tid] = sigs
        for sig in sigs:
            chars = [c for c in sig if '一' <= c <= '鿿']
            seen = set()
            for i in range(len(chars) - 3):
                qg = chars[i] + chars[i+1] + chars[i+2] + chars[i+3]
                if qg not in seen:
                    seen.add(qg)
                    gram_index[qg].append((tid, sig))

    # Match against input text
    input_sig = strip_all(norm_num(text))
    input_chars = [c for c in input_sig if '一' <= c <= '鿿']
    input_grams = set()
    for i in range(len(input_chars) - 3):
        input_grams.add(input_chars[i] + input_chars[i+1] + input_chars[i+2] + input_chars[i+3])

    if not input_grams:
        return JSONResponse({"success": True, "matches": [], "count": 0})

    hit_map = Counter()
    for qg in input_grams:
        if qg in gram_index:
            for tid, sig in gram_index[qg]:
                hit_map[tid] += 1

    scored = []
    for tid, hits in hit_map.items():
        tpl_grams = set()
        for s in tpl_sigs.get(tid, set()):
            tc = [c for c in s if '一' <= c <= '鿿']
            for i in range(len(tc) - 3):
                tpl_grams.add(tc[i] + tc[i+1] + tc[i+2] + tc[i+3])
        inter = len(input_grams & tpl_grams)
        union = max(1, len(input_grams | tpl_grams))
        jaccard = inter / union
        if jaccard >= 0.15:
            info = tpl.get(tid, {})
            scored.append({
                "id": tid,
                "text": info.get('text', ''),
                "category": info.get('category', ''),
                "jaccard": round(jaccard, 3),
                "hits": hits,
                "variables": info.get('variables', []),
            })

    scored.sort(key=lambda x: -x['jaccard'])

    return JSONResponse({
        "success": True,
        "matches": scored[:5],
        "count": len(scored),
    })
