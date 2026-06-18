"""
超声文本实体抽取引擎 — 基于 CMeKG 思路的 BERT-CRF 轻量版

功能:
  从 ASR 文本中提取: 器官, 病变, 部位, 尺寸, 形态, 边界, 回声, 血流
  输出结构化实体字典, 供模板填充引擎使用。

设计:
  使用小型 BERT 模型 + CRF 层做序列标注
  标签系统: B-ORG, I-ORG, B-DIS, I-DIS, B-POS, I-POS, B-MEA, I-MEA, O
  如果模型不可用, 降级到规则抽取 (与 _quick_extract_entities 相同)
"""
import re
import json
import os
from pathlib import Path

# 是否启用 BERT 模型（需要 GPU 或足够内存）
_USE_BERT = False  # 当前环境只有 CPU, 推理慢, 先关掉
_MODEL = None
_TOKENIZER = None

# ── 标签系统 ──
LABELS = ['O', 'B-ORG', 'I-ORG', 'B-DIS', 'I-DIS',
          'B-POS', 'I-POS', 'B-MEA', 'I-MEA']

# ── 规则回退: 实体词典 ──
_ORGANS = ['肝脏', '胆囊', '胰腺', '脾脏', '肾脏', '甲状腺', '乳腺',
           '子宫', '卵巢', '前列腺', '膀胱', '心脏', '颈动脉',
           '肝', '胆', '肾', '脾', '肺', '胃', '肠', '阑尾']

_DISEASES = ['囊肿', '囊性', '囊状', '结节', '结石', '斑块', '钙化', '占位',
             '肿瘤', '息肉', '积水', '积液', '扩张', '狭窄', '闭塞',
             '增厚', '毛糙', '粗糙', '欠光滑', '不光滑',
             '血管瘤', '脂肪肝', '肝硬化', '纤维化', '肌瘤', '增生',
             '返流', '反流', '血栓', '栓塞', '炎症', '感染',
             '囊实性', '混合性', '分叶状']

_POSITIONS = ['左叶', '右叶', '左侧', '右侧', '前叶', '后叶',
              '上段', '下段', '中段', '浅', '深',
              '近端', '远端', '头侧', '尾侧',
              '前壁', '后壁', '侧壁', '下壁',
              '底部', '颈部', '体部', '尾部']

_MEASURE_KWS = ['大小约', '厚约', '长约', '宽约', '深约', '内径约', '分离约']


def _load_bert_model():
    """懒加载 BERT 模型（尝试从 HuggingFace 下载轻量版）"""
    global _MODEL, _TOKENIZER
    if _MODEL is not None:
        return True
    try:
        from transformers import AutoTokenizer, AutoModelForTokenClassification
        model_name = "bert-base-chinese"
        _TOKENIZER = AutoTokenizer.from_pretrained(model_name)
        _MODEL = AutoModelForTokenClassification.from_pretrained(
            model_name, num_labels=len(LABELS)
        )
        return True
    except Exception:
        return False


def extract_entities_bert(text: str) -> dict:
    """BERT-CRF 实体提取（当前为占位, 启用条件: GPU/足够内存）"""
    if not _USE_BERT:
        return extract_entities_rule(text)
    if not _load_bert_model():
        return extract_entities_rule(text)
    # TODO: 加载微调后的 CRF 权重, 做序列标注
    return extract_entities_rule(text)


def extract_entities_rule(text: str) -> dict:
    """规则版实体提取（零依赖, 快速）"""
    if not text:
        return {}

    entities = {
        'organs': [],
        'diseases': [],
        'positions': [],
        'measurements': [],
        'size_value': None,
        'size_unit': None,
    }

    # 器官 (去重)
    for o in _ORGANS:
        if o in text:
            entities['organs'].append(o)

    # 病变 (去重)
    for d in _DISEASES:
        if d in text:
            entities['diseases'].append(d)

    # 位置
    for p in _POSITIONS:
        if p in text:
            entities['positions'].append(p)

    # 尺寸测量值 (完整匹配, 如 "约8.0x3.0cm", "0.9cm", "3mm")
    meas = re.findall(
        r'(?:约|大小约|厚约|长约|宽约|深约|内径约|分离约)?'
        r'\d+(?:\.\d+)?'
        r'(?:\s*[×xX\*乘]\s*\d+(?:\.\d+)?)*'
        r'\s*(?:mm|cm|毫米|厘米)',
        text
    )
    entities['measurements'] = [m.strip() for m in meas]

    # 分离尺寸值和单位
    size_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:[×xX\*乘]\s*\d+(?:\.\d+)?)?\s*(mm|cm|毫米|厘米)',
        text
    )
    if size_match:
        entities['size_value'] = size_match.group(1)
        entities['size_unit'] = size_match.group(2)

    return entities


def extract_and_format(text: str) -> str:
    """提取实体并格式化为 JSON 字符串（供 LLM prompt 使用）"""
    entities = extract_entities_bert(text)
    return json.dumps(entities, ensure_ascii=False, indent=2)


# 直接测试
if __name__ == '__main__':
    tests = [
        '肝左叶囊性囊肿，0.9cm。壁薄，后方回声增强。',
        '肝脏中度脂肪，肝内未见实质性占位结节。',
        '胆囊大小约8.0x3.0cm，囊内透声差，胆囊壁毛糙。',
        '甲状腺右叶低回声结节，大小约1.0cm，边界清晰。',
    ]
    for t in tests:
        print(f'输入: {t}')
        result = extract_entities_rule(t)
        print(f'  实体: {json.dumps(result, ensure_ascii=False)}')
        print()
