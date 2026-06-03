"""中文数字 → 阿拉伯数字转换

支持:
    '二十二' → '22'
    '一百四十五' → '145'
    '两百三十' → '230'
    '五点八' → '5.8'
    '三十一点二' → '31.2'
"""

import re

_CN_NUM = {'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'百':100,'千':1000,'万':10000}
_CN_DECIMAL = re.compile(r'([零一二两三四五六七八九十百]+)点([零一二两三四五六七八九])')
_CN_UNIT_CHARS = set('十百千万')
_CN_PATTERN = re.compile(r'[零一二两三四五六七八九十百千万]+')

def cn_to_arabic(text: str) -> str:
    """将中文数字表达式转为阿拉伯数字

    处理:
    1. 中文整数: 二十二→22, 一百四十五→145, 两百三十→230
    2. 中文小数: 五点八→5.8, 三十一点二→31.2
    3. 混合文本: '中孕期二十二到二十六'→'中孕期22到26'
    """
    def _parse_cn(s):
        """解析纯中文数字串 → 阿拉伯数字"""
        if not s or all(c in _CN_UNIT_CHARS for c in s):
            # 纯单位: "十"→10, "百"→100
            total = 0
            for c in s:
                if c == '十': total = max(total * 10, 10)
                elif c == '百': total = max(total * 100, 100)
                elif c == '千': total = max(total * 1000, 1000)
            return str(total) if total else s

        # 累计值
        total = 0
        current = 0  # 当前正在累积的数字(未遇到单位前)

        for ch in s:
            if ch in _CN_UNIT_CHARS:
                unit_val = _CN_NUM[ch]
                if current == 0:
                    current = 1
                # 检查是否是"万"类大单位（此时应乘以总累计再加）
                if unit_val >= 10000:
                    total = (total + current) * unit_val
                    current = 0
                elif unit_val >= 10:
                    current = max(current, 1) * unit_val
                    total += current
                    current = 0
            elif ch in _CN_NUM:
                current = _CN_NUM[ch]
            else:
                return s

        total += current
        return str(total)

    # 先处理中文小数: "五点八"→"5.8", "三十一点二"→"31.2"
    def _replace_cn_decimal(m):
        s = m.group()
        parts = s.split('点')
        int_part = _parse_cn(parts[0])
        dec_part = str(_CN_NUM[parts[1]])
        return f"{int_part}.{dec_part}"

    text = _CN_DECIMAL.sub(_replace_cn_decimal, text)

    # 再处理中文整数: "两百三十"→"230"
    return _CN_PATTERN.sub(lambda m: _parse_cn(m.group()), text)
