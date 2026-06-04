"""知识库加载器 — 统一加载所有规则库 JSON 文件

使用方式:
    from knowledge.loader import load_knowledge
    kb = load_knowledge()
    # kb.confusion_dict → ASR 混淆词典 {}
    # kb.confusion_dict_ext → HIS 扩展混淆词典 {}
    # kb.normal_ranges → HIS 正常值范围与诊断标准 {}
    # kb.report_structures → 按检查类型的报告段落结构 {}
    # kb.operational_stats → HIS 阳性率/运营统计 {}
    # kb.measurements → 胎儿测量模式 [(pattern, field), ...]
    # kb.site_disease → 部位-病变映射 {}
    # kb.manual_mapping → 手工关键词映射 {}
    # kb.unit_rules → 单位转换规则 []
"""

import json
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent

class KnowledgeBase:
    __slots__ = ('confusion_dict', 'confusion_dict_ext', 'normal_ranges',
                 'report_structures', 'operational_stats', 'drug_ultrasound_rules',
                 'asr_language_model',
                 'measurements', 'site_disease',
                 'manual_mapping', 'unit_rules')

    def __init__(self):
        self.confusion_dict = {}
        self.confusion_dict_ext = {}
        self.normal_ranges = {}
        self.report_structures = {}
        self.operational_stats = {}
        self.drug_ultrasound_rules = {}
        self.asr_language_model = {}
        self.measurements = []
        self.site_disease = {}
        self.manual_mapping = {}
        self.unit_rules = {}

    def __repr__(self):
        return (f"KnowledgeBase(confusion={len(self.confusion_dict)}, "
                f"confusion_ext={len(self.confusion_dict_ext)}, "
                f"normal_ranges={bool(self.normal_ranges)}, "
                f"report_structures={bool(self.report_structures)}, "
                f"op_stats={bool(self.operational_stats)}, "
                f"drug_rules={bool(self.drug_ultrasound_rules)}, "
                f"asr_lm={bool(self.asr_language_model)}, "
                f"measurements={len(self.measurements)}, "
                f"site_disease={len(self.site_disease)}, "
                f"manual={len(self.manual_mapping)}, "
                f"unit_rules={len(self.unit_rules)})")


def _load_json(name: str) -> dict:
    path = KNOWLEDGE_DIR / name
    if not path.exists():
        print(f"[knowledge] WARNING: {name} not found")
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_knowledge() -> KnowledgeBase:
    """加载所有知识库 JSON 文件"""
    kb = KnowledgeBase()

    # === ASR 纠错 ===
    kb.confusion_dict = _load_json("confusion_dict.json")
    kb.confusion_dict_ext = _load_json("confusion_dict_his_ext.json")

    # === HIS 正常值范围与诊断标准 (NEW) ===
    kb.normal_ranges = _load_json("normal_ranges.json")

    # === 报告结构模板 (NEW) ===
    kb.report_structures = _load_json("report_structures.json")

    # === 运营统计数据 (NEW) ===
    kb.operational_stats = _load_json("operational_stats.json")

    # === 药品-超声关联规则 (NEW) ===
    kb.drug_ultrasound_rules = _load_json("drug_ultrasound_rules.json")

    # === ASR语言模型增强 (NEW) ===
    kb.asr_language_model = _load_json("asr_language_model.json")

    # === 测量模式 ===
    raw_meas = _load_json("measurements.json")
    if isinstance(raw_meas, list):
        kb.measurements = [(m['pattern'], m['field']) for m in raw_meas]

    # === 部位-病变映射 ===
    kb.site_disease = _load_json("site_disease.json")

    # === 手工映射 ===
    kb.manual_mapping = _load_json("manual_mapping.json")

    # === 单位转换规则 ===
    kb.unit_rules = _load_json("unit_conversion.json")

    return kb


# 全局单例（避免重复加载）
_kb_instance = None

def get_kb() -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = load_knowledge()
    return _kb_instance
