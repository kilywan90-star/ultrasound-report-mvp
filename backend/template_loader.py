"""正式超声报告模板加载器 — v3"""

import csv, os, re
from pathlib import Path
from collections import defaultdict, OrderedDict

TEMPLATE_DIR = Path(os.environ.get("TEMPLATE_DIR", "") or "knowledge")
TEMPLATE_CSV = TEMPLATE_DIR / "1长沙范本.csv"

_template_index: OrderedDict[str, dict] = OrderedDict()
_templates_loaded = False
_keyword_index: dict[str, str] = {}
_category_index: dict[str, list[str]] = defaultdict(list)
_module_index: dict[str, list[str]] = defaultdict(list)



def _infer_module(name, info1, info2):
    """从模板内容推断器官模块"""
    text = (name or '') + ' ' + (info1 or '') + ' ' + (info2 or '')
    # 器官→模块映射
    organ_module = {
        '子宫': '子宫', '卵巢': '附件', '宫颈': '子宫', '内膜': '子宫', '盆腔': '子宫',
        '胎儿': '产科', '孕囊': '产科', '胎盘': '产科', '羊水': '产科', '脐带': '产科', '胎心': '产科',
        '前列腺': '前列腺', '膀胱': '泌尿', '肾': '肾脏', '输尿管': '泌尿',
        '甲状腺': '甲状腺', '乳腺': '乳腺', '腋窝': '乳腺',
        '二尖瓣': '心脏', '三尖瓣': '心脏', '主动脉瓣': '心脏', '心包': '心脏',
        '心室': '心脏', '心房': '心脏', '室间隔': '心脏', '肺动脉': '心脏',
        '肝脏': '肝脏', '胆囊': '胆道', '胰腺': '胰腺', '脾脏': '脾脏',
        '颈动脉': '周围血管', '椎动脉': '周围血管', '动脉': '周围血管', 'IMT': '周围血管',
        '大脑': '颅脑', '基底动脉': '颅脑', '经颅': '颅脑',
        '睾丸': '男生殖系', '附睾': '男生殖系', '阴囊': '男生殖系',
        '关节': '骨肌系统', '骨骼': '骨肌系统', '肌腱': '骨肌系统',
        '肺': '胸部', '胸腔': '胸部', '胸膜': '胸部',
        '眼球': '眼部', '视网膜': '眼部',
    }
    scores = {}
    for organ, mod in organ_module.items():
        if organ in text:
            scores[mod] = scores.get(mod, 0) + 1
    if scores:
        return max(scores, key=scores.get)
    return '其他'


def load_templates() -> OrderedDict[str, dict]:
    """加载超声模板CSV到内存（懒加载，只加载一次）"""
    global _templates_loaded, _template_index, _keyword_index, _category_index, _module_index

    if _templates_loaded:
        return _template_index

    if not TEMPLATE_CSV.exists():
        print(f"[模板加载] WARNING: 模板文件不存在: {TEMPLATE_CSV}")
        _templates_loaded = True
        return _template_index

    with open(TEMPLATE_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("DISCNAME") or "").strip()
            if not name or name in ("0", "NULL"):
                continue

            info1 = (row.get("INFO1") or "").strip()
            info2 = (row.get("INFO2") or "").strip()
            module = (row.get("MODULENAME") or "其他").strip()
            group = (row.get("DISCGROUP") or "").strip()
            visc = (row.get("VISCNAME") or "").strip()

            module = (row.get("MODULENAME") or "").strip()
            if not module or module == "NULL" or module.strip() == "":
                module = _infer_module(name, info1, info2)

            # 过滤无用的"噪音"模板 (INFO1太短或纯数字代码)
            if len(info1) < 20:
                # 检查info1是否有结构性超声文本 (含器官/测量/描述词)
                organ_kw = ['经','探查','位','大小','回声','见','mm','cm','正常','异常']
                if not any(kw in info1 for kw in organ_kw):
                    continue

            entry = {
                "name": name,
                "info1": info1,
                "info2": info2,
                "module": module,
                "group": group,
                "visc": visc,
            }

            _template_index[name] = entry

            # 关键词索引
            clean = re.sub(r"[\[\(（].*?[\]\)）\*]", "", name).strip()
            if clean:
                _keyword_index[clean] = name
            _keyword_index[name] = name

            # 从info1提取额外关键词 (如"双肾"、"集合系统")
            if info1:
                info_keywords = re.findall(r'[双两][侧肾]|[双两]侧[输卵子肾]|实质回声|大小形态|回声均匀|未见[异常占位]', info1)
                for kw in info_keywords:
                    if kw not in _keyword_index:
                        _keyword_index[kw] = name
            # 额外: 如果模板名含"正常"且info1含"双肾"+"集合系统"，增加专属关键词
            if '正常' in name and info1 and ('双肾' in info1 or '集合系统' in info1):
                _keyword_index['肾正常'] = name
                _keyword_index['双肾正常'] = name
                _keyword_index['双肾'] = name  # 覆盖"双肾"指向，保障优先命中正常肾模板

            # 类别索引
            if group:
                _category_index[group].append(name)
            if module:
                _module_index[module].append(name)

    _templates_loaded = True
    print(f"[模板加载] 超声模板: {len(_template_index)}条, "
          f"{len(_module_index)}个模块, {len(_category_index)}个分组")
    return _template_index


def get_template_by_name(name: str) -> dict | None:
    """精确获取一条模板的完整信息"""
    load_templates()
    return _template_index.get(name)


def search_candidates(text: str, exam_type: str = "", limit: int = 10, category: str = None) -> list[dict]:
    """
    从4871条模板中搜索候选模板列表
    策略: 关键词匹配 DISCNAME + 模块名过滤
    可选: category 限制搜索范围（按器官分类）
    """
    load_templates()
    if not _template_index:
        return []

    scored: dict[str, int] = {}

    from rule_engine import get_rule as _gr
    organ_words = _gr("templates.organ_words", ["肝脏","胆囊","胰腺","脾脏","肾脏","子宫","卵巢"])

    # 策略1: DISCNAME关键词精确匹配
    for keyword in sorted(_keyword_index.keys(), key=len, reverse=True):
        if keyword in text and len(keyword) >= 2:
            name = _keyword_index[keyword]
            # P0-2: 异常模板需证据——DISCNAME含疾病词时必须有ASR文本证据
            abnormal_kw = ["癌","瘤","结石","囊肿","增生","钙化","硬化","异位","梗塞","血栓","积水","腹水","畸形","占位","肿物","团块"]
            entry = _template_index.get(name, {})
            is_abnormal = any(kw in keyword for kw in abnormal_kw)
            extra_bonus = 0
            if is_abnormal:
                # 检查文本中是否有匹配的疾病关键词
                has_evidence = any(kw in text for kw in abnormal_kw)
                if has_evidence:
                    extra_bonus = 20  # 有证据加成
                else:
                    extra_bonus = -50  # 无证据强扣分
            scored[name] = max(scored.get(name, 0), 100 + len(keyword) * 5 + extra_bonus)

        # P0-3: "正常"关键词匹配——文本含"正常"时给正常模板加成
    normal_words = ["正常", "大小正常", "光滑", "光整", "规则", "均匀", "清晰", "通畅", "可"]
    has_normal_signal = any(w in text for w in normal_words)
    if has_normal_signal:
        for name, entry in _template_index.items():
            entry_text = (entry.get("name", "") + entry.get("info1", ""))[:100]
            if "正常" in name and any(w in text for w in ["正常","大小正常","光滑"]):
                scored[name] = max(scored.get(name, 0), 120)
            # 文本含器官词且模板名含"正常"时保底加分
            if "正常" in name:
                for organ in organ_words:
                    if organ in text and organ in (entry.get("info1","") + entry.get("name","")):
                        scored[name] = max(scored.get(name, 0), 80)
                        break
                # 额外: 匹配"双肾"、"集合系统"等字段
                extra_kidney_words = ["双肾", "集合系统", "肾"]
                if any(kw in entry.get("info1","")[:200] for kw in extra_kidney_words) and \
                   any(kw in text for kw in ["双肾", "集合系统", "肾", "肾"]):
                    scored[name] = max(scored.get(name, 0), 100)
                # 直接匹配: 如果文本含"双肾"且模板info1含"双肾"
                if "双肾" in text:
                    if "双肾" in (entry.get("info1","") + entry.get("name",""))[:300]:
                        scored[name] = max(scored.get(name, 0), 140)  # 提高到140超过其他正常模板
                if "集合系统" in text:
                    if "集合系统" in (entry.get("info1","") + entry.get("name",""))[:300]:
                        scored[name] = max(scored.get(name, 0), 140)

        # 策略1.5: 模板匹配关键词精确匹配 (master_rules.json)
    from rule_engine import get_rule as _gr2
    match_kw_dict = _gr2("templates.match_keywords", {})
    if match_kw_dict:
        for tpl_name, keywords in match_kw_dict.items():
            for kw in keywords:
                if kw in text and len(kw) >= 2:
                    if tpl_name in _template_index:
                        scored[tpl_name] = max(scored.get(tpl_name, 0), 200)  # 最高优先级
                        break

    # 策略2: 器官词匹配INFO1 (从规则引擎加载)
    from rule_engine import get_rule as _gr
    organ_words = _gr("templates.organ_words", ["肝脏","胆囊","胰腺","脾脏","肾脏","子宫","卵巢"])
    for name, entry in _template_index.items():
        info1 = entry.get("info1", "")
        for organ in organ_words:
            if organ in text and organ in info1:
                scored[name] = scored.get(name, 0) + 20
                break

    # 策略3: 疾病词匹配
    disease_words = _gr("templates.disease_words", ["结石","囊肿","肌瘤","息肉","增生","钙化"])
    for name, entry in _template_index.items():
        info1 = entry.get("info1", "") + entry.get("info2", "")
        for disease in disease_words:
            if disease in text and disease in info1:
                scored[name] = scored.get(name, 0) + 15
                break

    # 策略4: 检查类型模糊匹配模块名 (从规则引擎加载)
    module_map = _gr("templates.module_map", {"腹部": ["UIS"]})
    matched_modules = set()
    for kw, mods in module_map.items():
        if kw in exam_type or kw in text[:80]:
            matched_modules.update(mods)

    # P0-1: 跨模块守卫——模板器官词与文本器官词完全不匹配则扣分
    organ_module_map = {
        "前列腺": ["前列腺","膀胱","肾","精囊","睾丸","附睾","男生殖系"],
        "子宫": ["子宫","卵巢","附件","宫颈","盆腔","内膜","输卵管","阴道"],
        "乳腺": ["乳腺","腋窝"],
        "甲状腺": ["甲状腺","甲状旁腺","峡部","颈部"],
        "心脏": ["心室","心房","瓣","室间隔","心包","主动脉","肺动脉","二尖瓣","三尖瓣"],
        "颈动脉": ["颈动脉","椎动脉","IMT","颈总","颈内","颈外","内膜中层"],
        "TCD": ["大脑","基底动脉","椎动脉","经颅","MCA","ACA","PCA","BA"],
        "胎儿": ["胎儿","孕囊","胎盘","羊水","脐带","胎心","BPD"],
    }
    # 确定文本属于哪个器官类别
    text_organ_categories = set()
    for cat, organs in organ_module_map.items():
        if any(o in text for o in organs):
            text_organ_categories.add(cat)

    for name in list(_template_index.keys()):
        entry = _template_index[name]
        mod = entry.get("module", "")
        # 模块匹配加分 (有明确模块名的模板优先)
        if mod and mod in matched_modules:
            scored[name] = scored.get(name, 0) + 60
        elif not mod or not mod.strip():
            scored[name] = scored.get(name, 0) - 20

        # P0-1: 跨模块守卫——模板所属器官类别与文本器官类别不匹配则扣分
        if text_organ_categories and name in scored:
            tpl_text = entry.get("info1", "") + entry.get("name", "")
            tpl_categories = set()
            for cat, organs in organ_module_map.items():
                if any(o in tpl_text for o in organs):
                    tpl_categories.add(cat)
            # 更严格的守卫: 如果模板INFO1中没有任何文本中的器官词 → 强扣分
            tpl_has_text_organ = any(o in tpl_text for o in organ_words)
            if not tpl_has_text_organ:
                scored[name] -= 70
            elif tpl_categories and not tpl_categories.intersection(text_organ_categories):
                scored[name] -= 50

        # P0-1增强: 模板INFO1与文本完全不共享任何器官词 → 强制删除
        if name in scored:
            tpl_text_all = entry.get("info1", "") + entry.get("name", "")
            all_organs = set()
            for organs in organ_module_map.values():
                all_organs.update(organs)
            tpl_has_any_organ = any(o in tpl_text_all for o in all_organs)
            text_has_any_organ = any(o in text for o in all_organs)
            if text_has_any_organ and not tpl_has_any_organ:
                scored[name] -= 90
            if scored.get(name, 0) <= 0:
                del scored[name]

    # 策略5: 无模块名的模板只在有器官词命中时才保留
    for name in list(scored.keys()):
        if scored[name] <= 0:
            del scored[name]
            continue
        entry = _template_index.get(name, {})
        mod = entry.get("module", "")
        if not mod or not mod.strip():
            # 无模块名模板必须同时命中器官词+疾病词才保留
            has_organ = any(o in (entry.get("info1","") + entry.get("name","")) for o in organ_words)
            has_disease = any(d in (entry.get("info1","") + entry.get("name","") + entry.get("info2","")) for d in disease_words)
            if not (has_organ and has_disease):
                scored[name] = scored.get(name, 0) - 30
                if scored[name] <= 0:
                    del scored[name]

    # 排序取top-N
    ranked = sorted(scored.items(), key=lambda x: -x[1])
    results = []
    for name, score in ranked[:limit * 2]:
        entry = _template_index[name]
        results.append({
            "name": name,
            "module": entry.get("module", ""),
            "group": entry.get("group", ""),
            "info1_preview": entry.get("info1", "")[:300],
            "score": score,
        })

    # 去重按name，截断limit
    seen = set()
    uniq = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            uniq.append(r)
        if len(uniq) >= limit:
            break

    return uniq


def all_module_names() -> list[str]:
    load_templates()
    return sorted(_module_index.keys())


def match_template(text: str, exam_type: str = "") -> dict | None:
    """根据文本匹配最合适的正式模板（保留旧接口兼容）"""
    candidates = search_candidates(text, exam_type, limit=1)
    if candidates:
        return get_template_by_name(candidates[0]["name"])
    return None


def match_templates_multi(text: str, exam_type: str = "", max_results: int = 3) -> list[dict]:
    """返回匹配到的多个模板"""
    candidates = search_candidates(text, exam_type, limit=max_results)
    return [get_template_by_name(c["name"]) for c in candidates if get_template_by_name(c["name"])]


def extract_options(text: str) -> list[list[str]]:
    return re.findall(r"\[([^\]]*?)\]", text)


def format_template_for_prompt(entry: dict) -> str:
    """将一条正式模板格式化为 LLM 参考文本"""
    parts = []
    if entry.get("info1"):
        info1_clean = re.sub(r"\[([^\]]+?)\]", r"[\1]", entry["info1"])
        info1_clean = info1_clean.replace("+", "\n")
        info1_clean = re.sub(r"\s{2,}", " ", info1_clean)
        info1_clean = info1_clean.replace("mm × mm × mm", "___mm × ___mm × ___mm")
        info1_clean = info1_clean.replace("mm X mm X mm", "___mm × ___mm × ___mm")
        info1_clean = re.sub(r"(?<!\d)mm(?![×Xx])", "___mm", info1_clean)
        parts.append(f"【所见格式参考】\n{info1_clean.strip()}")

    if entry.get("info2"):
        info2_clean = entry["info2"].replace("+", "\n")
        parts.append(f"【提示格式参考】\n{info2_clean.strip()}")

    return "\n\n".join(parts)


def all_disease_names() -> list[str]:
    load_templates()
    return sorted(set(_keyword_index.values()))


# 自动加载
load_templates()
