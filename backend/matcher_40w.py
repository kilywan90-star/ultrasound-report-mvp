"""
40万真实报告 Fallback 匹配器

按检查类型分片加载，当现有匹配引擎分数 < 0.5 时使用。
每片约 3-6MB，懒加载，不占用启动内存。
"""
import json
import re
import os
from pathlib import Path

_INDEX_DIR = Path(__file__).resolve().parent / "knowledge"

# 检查类型 → 索引文件名
BP_FILES = {
    '腹部超声': '40w_abdomen.json',
    '腹部': '40w_abdomen.json',
    '甲状腺超声': '40w_thyroid.json',
    '甲状腺': '40w_thyroid.json',
    '乳腺超声': '40w_breast.json',
    '乳腺': '40w_breast.json',
    '心脏超声': '40w_cardiac.json',
    '心脏': '40w_cardiac.json',
    '妇科超声': '40w_gynecology.json',
    '妇科': '40w_gynecology.json',
    '产科超声': '40w_gynecology.json',
    '泌尿超声': '40w_urology.json',
    '泌尿': '40w_urology.json',
    '血管超声': '40w_vascular.json',
    '血管': '40w_vascular.json',
}

# 各部位的默认（找不到对应部位时的回退）
_DEFAULT_BP = 'abdomen'

_cache = {}

# 常见停用词，过滤掉后不会对匹配产生区分
_STOPWORDS = {
    '可以','没有','什么','如果','因为','所以','而且','或者',
    '虽然','然后','比较','已经','可能','需要','应该','这些',
    '那些','就是','之后','之间','一种','主要','以及','排除',
    '左右','内径','可见','范围','显示','清楚','状态',
    '未见','明显','大小','正常','回声','均匀','规则','光滑',
}


def _ensure_loaded(exam_type: str) -> dict | None:
    """按需加载索引，懒加载 + 缓存"""
    if exam_type in _cache:
        return _cache[exam_type]

    bp_file = BP_FILES.get(exam_type)
    if not bp_file:
        return None

    filepath = _INDEX_DIR / bp_file
    if not filepath.exists():
        return None

    try:
        with open(str(filepath), 'r', encoding='utf-8') as f:
            data = json.load(f)
        _cache[exam_type] = data
        return data
    except Exception:
        return None


def match_40w(text: str, exam_type: str, top_n: int = 5) -> list[dict]:
    """匹配40万真实报告源，返回最多 top_n 个候选。

    每个候选:
      score: 0.0 ~ 1.0
      see: 超声所见
      hint: 超声提示
    """
    if not text or not text.strip():
        return []

    data = _ensure_loaded(exam_type)
    if not data:
        return []

    records = data['records']
    index = data['index']

    # 提取输入文本关键词
    text_clean = re.sub(r'\s+', '', text)
    words = set(re.findall(r'[一-鿿]{2,5}', text_clean)) - _STOPWORDS
    if not words:
        return []

    # 关键词重叠计分
    scores = {}
    for w in words:
        if w not in index:
            continue
        for rec_id in index[w]:
            if rec_id not in scores:
                scores[rec_id] = {'score': 0, 'rec': records[rec_id]}
            scores[rec_id]['score'] += 1

    if not scores:
        return []

    # 排名并归一化
    ranked = sorted(scores.values(), key=lambda x: -x['score'])[:top_n]
    max_s = ranked[0]['score'] if ranked else 1
    for r in ranked:
        r['score'] = round(r['score'] / max_s, 2)

    return [{'score': r['score'], 'see': r['rec']['s'], 'hint': r['rec']['h']} for r in ranked]
