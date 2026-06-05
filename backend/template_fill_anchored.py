#!/usr/bin/env python3
"""
Template Fill Engine v3 — 数值强保留版
原则:
  1. 保留模板占位符
  2. 语音中所有数值型内容(含单位)必须在报告中出现 —— 未匹配的追加到最后
  3. 语音中有但模板没有的描述性关键词也追加到最后
  4. 宁愿多报(多追加几条)也不漏报
"""

import re

def fill_template_keep_placeholders(raw_text: str, template_info1: str) -> str:
    result = template_info1
    if not template_info1:
        return f"<div class='rpt-html'>{raw_text}</div>"

    # ── Step 1: 选项填充 ([A;B;C] → 选匹配的) ──
    def pick_option(m):
        content = m.group(1)
        if ';' in content:
            parts = [p.strip() for p in content.split(';') if p.strip()]
            for p in parts:
                clean_p = re.sub(r'[\[\]\(\)（）\*]', '', p)
                if len(clean_p) >= 2 and clean_p in raw_text:
                    return p
            return m.group(0)
        return m.group(0)
    result = re.sub(r'\[([^\]]+(?:;[^\]]+)+)\]', pick_option, result)

    # ── Step 2: 提取语音中所有数值型内容 ──
    num_patterns = [
        r'(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)',
        r'(\d+(?:\.\d+)?)\s*(次/分|bpm)',
        r'(\d+(?:\.\d+)?)\s*(克|g|kg|公斤)',
        r'(\d+(?:\.\d+)?)\s*(平方厘米|cm²)',
        r'(\d+(?:\.\d+)?)\s*级',
        r'(\d+(?:\.\d+)?)\s*类',
        r'×\s*(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)?',
        r'(\d+(?:\.\d+)?)\s*×\s*(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)?',
    ]

    voice_measurements = []  # 所有数值+上下文
    for pat in num_patterns:
        for m in re.finditer(pat, raw_text):
            full = m.group(0)
            idx = m.start()
            ctx = raw_text[max(0, idx - 30):min(len(raw_text), idx + len(full) + 10)].strip()
            voice_measurements.append({"match": full, "context": ctx, "pos": idx})

    # ── Step 3: 模板中mm占位符填充 ──
    mm_count = len(re.findall(r'\bmm\b(?!\w)', result))
    pending_nums = [v for v in voice_measurements if 'mm' in v['match'] or 'cm' in v['match']]

    def fill_mm(m):
        nonlocal pending_nums
        if pending_nums:
            return pending_nums.pop(0)['match']
        return m.group(0)
    if mm_count > 0 and pending_nums:
        result = re.sub(r'\bmm\b(?!\w)', fill_mm, result)

    # ── Step 4: 标记未填充/已填充 ──
    result = re.sub(r'(___+\s*(?:mm|cm)?|未测)', r'<i class="unfill">\1</i>', result)

    def mark_voice(m):
        val = m.group(0)
        if '<' in val: return val
        return f'<b class="voice">{val}</b>'
    result = re.sub(r'\b\d+(?:\.\d+)?\s*(?:mm|cm|毫米|厘米|次/分|克|平方厘米|级|类)?', mark_voice, result)

    # ── Step 5: 强保底 —— 所有未出现在result中的数值必须追加 ──
    # 过滤掉已在填充模板中出现过的数值
    flat_result = re.sub(r'<[^>]+>', '', result)
    extra = []

    for vm in voice_measurements:
        match_val = vm['match']
        # 检查这个数值是否已经在填充后的结果中
        # 提取纯数字部分
        num_part = re.findall(r'\d+(?:\.\d+)?', match_val)
        if num_part:
            # 如果该数值的主数字不在result中，追加
            if not any(n in flat_result for n in num_part):
                extra.append(vm['context'])

    # 描述性关键词保底
    desc_kw = ["结石","囊肿","息肉","增生","钙化","反流","积水","积液",
               "斑块","狭窄","占位","团块","结节","硬化","腹水","扩张",
               "肿大","增厚","回声增强","回声减低","不规则","毛糙","模糊",
               "无回声","低回声","高回声","混合回声","实性","囊性",
               "BI-RADS","TI-RADS","包膜","边界","血流","淋巴"]
    for kw in desc_kw:
        if kw in raw_text and kw not in flat_result:
            idx = raw_text.find(kw)
            start = max(0, idx - 15)
            end = min(len(raw_text), idx + 20)
            extra.append(raw_text[start:end].strip())

    if extra:
        # 去重
        seen = set()
        unique = []
        for e in extra:
            norm = re.sub(r'\s+', '', e)[:30]
            if norm not in seen:
                seen.add(norm)
                unique.append(e)

        result += '\n<div class="rpt-sec"><b class="rpt-label">补充数据（语音中有但模板无对应字段）</b>\n'
        for e in unique[:15]:
            result += f'<div style="margin:2px 0;color:#64748b;font-size:11px">* {e}</div>\n'
        result += '</div>'

    return f"<div class='rpt-html'>{result}</div>"


def fill_anchored(raw_text: str, template_info1: str) -> str:
    return fill_template_keep_placeholders(raw_text, template_info1)
