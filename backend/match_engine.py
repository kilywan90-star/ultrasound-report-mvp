"""40万超声报告数据库 — 智能匹配引擎
加载全字段40万-matching_result_clean.csv, 按器官索引,
提供关键词+数字+方言的快速匹配, 返回TopN候选及置信度
"""
import csv, sys, os, re, json
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CSV_PATH = _HERE / "knowledge" / "40万_matching_index.json"

# 全局缓存
_RECORDS = None
_BY_ORGAN = None
_LOADED = False

# 方言映射
DIALECT_MAP = {
    '石头':'结石','水泡泡':'囊肿','水泡子':'囊肿','包包':'结节',
    '坨坨':'结节','腰子':'肾脏','颈子':'甲状腺','石脑':'结石',
    '头头':'颈部','奶子':'乳腺','胆颈颈':'胆囊颈部','胆底底':'胆囊底部',
    '胆体体':'胆囊体部','点八':'0.8','点九':'0.9','点七':'0.7','点六':'0.6',
    '点五':'0.5','点四':'0.4','点三':'0.3','点二':'0.2','点一':'0.1',
}

# 器官列表
ORGANS = ['乳腺','甲状腺','胆囊','肝脏','肾','子宫','心脏','颈动脉','膀胱','前列腺','脾','胰腺']

def _load_csv():
    """从CSV加载并预索引"""
    global _RECORDS, _BY_ORGAN, _LOADED
    if _LOADED:
        return

    csv_path = _CSV_PATH.parent / "全字段40万-matching_result_clean.csv"
    if not csv_path.exists():
        # 尝试桌面路径
        csv_path = Path(r'C:\Users\Administrator\Desktop\40万超声数据挖掘\全字段40万-matching_result_clean.csv')
    if not csv_path.exists():
        print(f"[匹配引擎] CSV不存在: {csv_path}")
        _LOADED = True
        return

    with open(csv_path, 'r', encoding='gbk') as f:
        content = f.read()
    fixed = re.sub(r'"[^"]*"', lambda m: m.group(0).replace('\n', ' '), content)
    reader = csv.DictReader(fixed.splitlines())

    records = []
    for i, row in enumerate(reader):
        if i >= 50000: break
        see = (row.get('rpt_StudySee超声所见（精简版）') or row.get('rpt_StudySee','') or '').strip()
        info1 = (row.get('tpl_INFO1 模板扩展信息 1') or row.get('tpl_INFO1','') or '').strip()
        see_full = (row.get('rpt_StudySee_Full超声所见（完整版）') or row.get('rpt_StudySee_Full','') or '').strip()
        discname = (row.get('discname 诊断名称') or row.get('discname','') or '').strip()
        discgroup = (row.get('discgroup 诊断分组') or row.get('discgroup','') or '').strip()
        if see and len(see) >= 5 and info1:
            records.append({
                'see': see[:200], 'info1': info1[:500],
                'see_full': see_full[:500], 'discname': discname[:100],
                'discgroup': discgroup[:50]
            })

    # 按器官索引
    by_organ = defaultdict(list)
    for rec in records:
        matched = False
        for o in ORGANS:
            if o in rec['see'] or o in rec['discname']:
                by_organ[o].append(rec)
                matched = True
        if not matched:
            by_organ['其他'].append(rec)

    _RECORDS = records
    _BY_ORGAN = dict(by_organ)
    _LOADED = True
    print(f"[匹配引擎] 加载 {len(records)} 条, {len(by_organ)} 个器官索引")


def _normalize(text: str) -> str:
    """标准化文本: 方言转换+去标点"""
    t = text
    for wrong, right in DIALECT_MAP.items():
        t = t.replace(wrong, right)
    t = t.replace('×','x').replace('，','').replace('。','')
    t = t.replace('（','').replace('）','').replace(' ','')
    return t


def score_match(input_text: str, rec: dict) -> int:
    """评分: ASR输入 vs 数据库记录"""
    s = 0
    # 方言加分
    for wrong, right in DIALECT_MAP.items():
        if wrong in input_text and right in rec['see']:
            s += 15
    text = _normalize(input_text)
    see = _normalize(rec['see'])

    # 关键词评分(2-3字分片)
    for i in range(len(text)-1):
        kw = text[i:i+2]
        if kw in see: s += 2
    for i in range(len(text)-2):
        kw = text[i:i+3]
        if kw in see: s += 5

    # 数字命中
    nums_in = set(re.findall(r'\d+(?:\.\d+)?', text))
    nums_rec = set(re.findall(r'\d+(?:\.\d+)?', see))
    s += len(nums_in & nums_rec) * 5

    # 器官加成
    for o in ORGANS:
        if o[:2] in text and o[:2] in see:
            s += 20

    # 位置/方位词加成
    directions = {'外上':'外上','内上':'内上','外下':'外下','内下':'内下',
                  '下极':'下极','上极':'上极','中极':'中极','前壁':'前壁','后壁':'后壁'}
    for d_kw, d_val in directions.items():
        if d_kw in text and d_kw in see:
            s += 8

    # BI-RADS/TI-RADS分级加成
    grades = re.findall(r'[二三四]类|BIRADS|TIRADS|[2-4][abABC]?', text)
    for g in grades:
        if g in see:
            s += 10

    return s


def search(input_text: str, top_n: int = 5) -> list[dict]:
    """搜索接口: 返回TopN候选"""
    _load_csv()
    if not _RECORDS:
        return []

    # 确定器官范围
    target_organs = [o for o in ORGANS if o[:2] in input_text]
    candidates = []
    for o in (target_organs if target_organs else ORGANS):
        candidates.extend(_BY_ORGAN.get(o, [])[:500])

    # 评分
    scored = [(score_match(input_text, rec), rec) for rec in candidates]
    scored.sort(key=lambda x: -x[0])

    results = []
    for score, rec in scored[:top_n]:
        if score > 0:
            results.append({
                'confidence': min(round(score / 70 * 100), 98),
                'score': score,
                'discname': rec['discname'],
                'discgroup': rec['discgroup'],
                'see': rec['see'][:200],
                'info1': rec['info1'][:500],
                'see_full': rec['see_full'][:500],
            })

    return results


def auto_match(input_text: str) -> dict | None:
    """自动匹配: 置信度独占超过阈值时触发"""
    results = search(input_text, top_n=3)
    if len(results) >= 2:
        r0, r1 = results[0], results[1]
        ratio = r0['score'] / max(r1['score'], 1)
        diff = r0['score'] - r1['score']
        if (ratio >= 1.3 or diff >= 10) and r0['score'] >= 15:
            return r0
    # 单候选且有分
    if len(results) >= 1 and results[0]['score'] >= 20:
        return results[0]
    return None


if __name__ == '__main__':
    _load_csv()
    tests = [
        '右乳外上0.8×0.5低回声边界清无血流二类',
        '胆囊头头有个1.2的石头壁不厚',
        '甲状腺右叶0.4的水泡泡边界清二类',
        '右肾下极0.5强回声后方伴声影',
        '子宫前位肌层1.5×1.2低回声边界清',
    ]
    for text in tests:
        print(f'\n=== 输入: {text} ===')
        result = auto_match(text)
        top3 = search(text, 3)
        for i, r in enumerate(top3):
            print(f'  #{i+1} conf={r["confidence"]}%  {r["discname"][:30]}')
        if result:
            print(f'  ✅ 自动触发: {result["discname"]}')
        else:
            print(f'  ⚠️ 未触发')
