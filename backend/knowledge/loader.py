"""知识库加载器 — 统一加载所有规则库 JSON 文件

使用方式:
    from knowledge.loader import load_knowledge
    kb = load_knowledge()
    # kb.confusion_dict → ASR 混淆词典 {}
    # kb.confusion_dict_ext → HIS 扩展混淆词典 {}
    # kb.normal_ranges → HIS 正常值范围与诊断标准 {}
    # kb.grading_standards → BI-RADS/TI-RADS 分级标准 {}
    # kb.high_risk_signs → 高风险征象规则 {}
    # kb.sex_guard_rules → 性别守卫规则 {}
    # kb.normal_thresholds → 数值阈值规则 {}
"""

import json
import threading
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent
_lock = threading.Lock()


class KnowledgeBase:
    __slots__ = (
        'confusion_dict', 'confusion_dict_ext',
        'normal_ranges', 'normal_thresholds', 'ultrasound_value_rules',
        'report_structures', 'operational_stats',
        'drug_ultrasound_rules', 'asr_language_model',
        'pregnancy_ga_constraints',
        'measurements', 'site_disease',
        'manual_mapping', 'unit_rules',
        'antonym_pairs', 'cross_validation',
        'changsha_hospital_templates',
        # === 新补全的加载项 ===
        'grading_standards',          # BI-RADS/TI-RADS 分级标准
        'high_risk_signs',            # 高风险征象检测规则
        'sex_guard_rules',            # 性别守卫规则
        'negative_description_bank',  # 正常描述词库
        'exam_part_routing',          # 检查部位路由
        'extended_hotword_index',     # 扩展热词索引
        'high_conf_candidates',       # 高置信候选模板
        'matching_rules_merged',      # 匹配规则合并版
        'template_score_rules',       # 模板评分规则
        'asr_fallback_config',        # ASR降级策略
        'health_tips_bank',           # 健康建议库
        'dialect_icd10_map',          # 方言→ICD10映射
        'dialect_term_map',           # 方言术语映射
        'quality_dashboard',          # 质量看板配置
        'quality_metrics',            # 质量指标
        'drg_dip_codes',              # DRG/DIP编码
        'loinc_codes',                # LOINC编码
        'fewshot_from_real_reports',  # 真实报告 few-shot
        'llm_fewshot_examples',       # LLM few-shot
        'llm_fewshot_examples_v2',    # LLM few-shot v2
    )

    def __init__(self):
        self.confusion_dict = {}
        self.confusion_dict_ext = {}
        self.normal_ranges = {}
        self.normal_thresholds = {}
        self.ultrasound_value_rules = {}  # 桌面40万数值知识库
        self.report_structures = {}
        self.operational_stats = {}
        self.drug_ultrasound_rules = {}
        self.asr_language_model = {}
        self.pregnancy_ga_constraints = {}
        self.measurements = []
        self.site_disease = {}
        self.manual_mapping = {}
        self.unit_rules = {}
        self.antonym_pairs = {}
        self.cross_validation = {}
        # 新补全
        self.grading_standards = {}
        self.high_risk_signs = {}
        self.sex_guard_rules = {}
        self.negative_description_bank = {}
        self.exam_part_routing = {}
        self.extended_hotword_index = {}
        self.high_conf_candidates = {}
        self.matching_rules_merged = {}
        self.template_score_rules = {}
        self.asr_fallback_config = {}
        self.health_tips_bank = {}
        self.dialect_icd10_map = {}
        self.dialect_term_map = {}
        self.quality_dashboard = {}
        self.quality_metrics = {}
        self.drg_dip_codes = {}
        self.loinc_codes = {}
        self.fewshot_from_real_reports = {}
        self.llm_fewshot_examples = {}
        self.llm_fewshot_examples_v2 = {}
        self.changsha_hospital_templates = {}  # 长沙医院模板

    def __repr__(self):
        loaded = []
        for attr in self.__slots__:
            v = getattr(self, attr, None)
            if isinstance(v, dict) and len(v) > 0:
                loaded.append(attr)
            elif isinstance(v, list) and len(v) > 0:
                loaded.append(attr)
        return f"KnowledgeBase(loaded={len(loaded)}/{len(self.__slots__)}: {', '.join(loaded[:10])}{'...' if len(loaded)>10 else ''})"


def _load_json(name: str) -> dict:
    """加载JSON，兼容UTF-8和GBK编码"""
    path = KNOWLEDGE_DIR / name
    if not path.exists():
        return {}
    # 先试UTF-8
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(path, encoding='gbk') as f:
            return json.load(f)


def load_knowledge() -> KnowledgeBase:
    """加载所有知识库 JSON 文件"""
    kb = KnowledgeBase()

    # === ASR 纠错 ===
    kb.confusion_dict = _load_json("confusion_dict.json")
    kb.confusion_dict_ext = _load_json("confusion_dict_his_ext.json")

    # === ASR 热词与语言模型 ===
    kb.asr_language_model = _load_json("asr_language_model.json")
    kb.asr_fallback_config = _load_json("asr_fallback_config.json")
    kb.extended_hotword_index = _load_json("extended_hotword_index.json")

    # === 数值与阈值 ===
    kb.normal_ranges = _load_json("normal_ranges.json")
    kb.normal_thresholds = _load_json("normal_thresholds.json")
    kb.ultrasound_value_rules = _load_json("超声数值知识库-ultrasound_value_rules.json")

    # === 报告结构 ===
    kb.report_structures = _load_json("report_structures.json")
    kb.negative_description_bank = _load_json("negative_description_bank.json")
    kb.fewshot_from_real_reports = _load_json("fewshot_from_real_reports.json")

    # === 长沙医院模板 ===
    kb.changsha_hospital_templates = _load_json("长沙医院模板_提取结果.json")

    # === 运营与质量 ===
    kb.operational_stats = _load_json("operational_stats.json")
    kb.quality_dashboard = _load_json("quality_dashboard.json")
    kb.quality_metrics = _load_json("quality_metrics.json")

    # === 药品-超声关联 ===
    kb.drug_ultrasound_rules = _load_json("drug_ultrasound_rules.json")

    # === 孕周约束 ===
    kb.pregnancy_ga_constraints = _load_json("pregnancy_ga_constraints.json")

    # === 分级标准 ===
    kb.grading_standards = _load_json("grading_standards.json")

    # === 高风险征象 ===
    kb.high_risk_signs = _load_json("high_risk_signs.json")

    # === 性别守卫 ===
    kb.sex_guard_rules = _load_json("sex_guard_rules.json")

    # === 测量模式 ===
    raw_meas = _load_json("measurements.json")
    if isinstance(raw_meas, list):
        kb.measurements = [(m['pattern'], m['field']) for m in raw_meas]

    # === 部位-病变映射 ===
    kb.site_disease = _load_json("site_disease.json")
    kb.exam_part_routing = _load_json("exam_part_routing.json")

    # === 手工映射与方言 ===
    kb.manual_mapping = _load_json("manual_mapping.json")
    kb.dialect_icd10_map = _load_json("dialect_icd10_map.json")
    kb.dialect_term_map = _load_json("dialect_term_map.json")

    # === 单位转换 ===
    kb.unit_rules = _load_json("unit_conversion.json")

    # === 矛盾检测 ===
    kb.antonym_pairs = _load_json("antonym_pairs.json")
    kb.cross_validation = _load_json("cross_validation.json")

    # === 模板匹配规则 ===
    kb.matching_rules_merged = _load_json("matching_rules_merged.json")
    kb.template_score_rules = _load_json("template_score_rules.json")
    kb.high_conf_candidates = _load_json("high_conf_candidates.json")

    # === 编码/标准 ===
    kb.drg_dip_codes = _load_json("drg_dip_codes.json")
    kb.loinc_codes = _load_json("loinc_codes.json")

    # === LLM few-shot ===
    kb.llm_fewshot_examples = _load_json("llm_fewshot_examples.json")
    kb.llm_fewshot_examples_v2 = _load_json("llm_fewshot_examples_v2.json")

    # === 健康建议 ===
    kb.health_tips_bank = _load_json("health_tips_bank.json")

    return kb


# 全局单例（避免重复加载）
_kb_instance = None


def get_kb() -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        with _lock:
            if _kb_instance is None:
                _kb_instance = load_knowledge()
    return _kb_instance


def reload_knowledge():
    """热重载所有知识库 JSON 文件 (无需重启服务)"""
    global _kb_instance
    with _lock:
        _kb_instance = load_knowledge()
    return _kb_instance
