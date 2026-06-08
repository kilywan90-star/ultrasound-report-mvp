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

# 路由分类 → 模板模块 映射表 (用于category过滤)
# routing/__init__.py 的 category 值 → template_loader 的 module 名
CATEGORY_MODULE_MAP: dict[str, list[str]] = {
    # 心脏: 专用模块25条
    "cardiac": ["心脏"],
    # 甲状腺: 专用模块29条
    "thyroid": ["甲状腺"],
    # 乳腺: 专用模块32条
    "breast": ["乳腺"],
    # 腹部: UIS(147条含肝胆胰脾肾) + 肝脏(4) + 胆囊(3) + 肾脏(17)
    "abdomen": ["UIS", "肝脏", "胆囊", "肾脏"],
    # 妇科: 子宫(22专用) + UIS(含子宫/卵巢分组)
    "gynecology": ["子宫", "UIS"],
    # 泌尿/前列腺: 前列腺(14专用) + 泌尿(12) + 男生殖系(5) + UIS(含前列腺分组)
    "urology": ["前列腺", "泌尿", "男生殖系", "UIS"],
    # 血管: 周围血管(34条)+部分UIS血管分组已包含在UIS中
    "vascular": ["周围血管"],
    # 脾脏: 专用模块12条
    "spleen": ["脾"],
    # fetal: 产科模板
    "fetal": ["产科"],
    # other: 不限分类, 全量搜索
}


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
                info_keywords = re.findall(r'[双两][侧肾]|[双两]侧[输卵子肾]|实质回声|大小形态|回声均匀(?![^，。；]*大小)|未见[异常占位]', info1)
                for kw in info_keywords:
                    if kw not in _keyword_index and len(kw) >= 4:  # 少于4字的关键词太通用
                        _keyword_index[kw] = name
            # 额外: 如果模板名含"正常"且info1含"双肾"+"集合系统"，增加专属关键词
            # 注意: 不覆盖"双肾"本身，让疾病模板也能匹配
            if '正常' in name and info1 and ('双肾' in info1 or '集合系统' in info1):
                _keyword_index['肾正常'] = name
                _keyword_index['双肾正常'] = name

        # 为异常模板添加人工关键词（模板名中没体现的）
        # 副脾 → 只需保留"副脾"关键词, 但"回声均匀"不应指向副脾
        # 解决方案: 对所有含"回声"的关键词, 只保留作为二级索引

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

    # ═══ Route 2: 按category限制搜索范围 ═══
    _valid_names: set[str] | None = None
    if category and category != "other" and category in CATEGORY_MODULE_MAP:
        _target_modules = set(CATEGORY_MODULE_MAP[category])
        _valid_names = {
            name for name, entry in _template_index.items()
            if entry.get("module", "") in _target_modules
        }
        # 空结果兜底: category过滤后没有模板 → 降级为全量搜索
        if not _valid_names:
            _valid_names = None  # fallback: 不限
    # 注: category=None/"other" 时不限, 保留340条全量搜索

    # 策略1: DISCNAME关键词精确匹配 (预过滤关键字列表, 加速category模式)
    _keyword_names = _keyword_index
    if _valid_names:
        # 建立反向索引: name → [keywords] 只需构建一次
        _name_to_keywords: dict[str, list[str]] = {}
        for kw, n in _keyword_index.items():
            _name_to_keywords.setdefault(n, []).append(kw)
        # 仅保留_valid_names中模板的关键词
        _keyword_names = {}
        for name in _valid_names:
            for kw in _name_to_keywords.get(name, []):
                _keyword_names[kw] = name
    # 器官词列表（用于全搜索函数）
    _ORGAN_WORDS = ["肝脏","胆囊","胰腺","脾脏","肾脏","子宫","卵巢","前列腺","甲状腺","乳腺","心脏","颈动脉","椎动脉","胎儿","膀胱","睾丸","附睾","淋巴结","阑尾","胸腔","腹腔","盆腔","胆总管","门静脉","胎心","胎盘","羊水","脐带"]
    # 否定信号检测: "已切除""未探及"等 → 降低正常模板得分
    _has_negation = any(kw in text for kw in ["已切除","切除","未探及","未扪及","术后"])
    for keyword in sorted(_keyword_names.keys(), key=len, reverse=True):
        if keyword in text and len(keyword) >= 2:
            name = _keyword_names[keyword]
            # P0-2: 异常模板需证据——DISCNAME含疾病词时必须有ASR文本证据
            abnormal_kw = ["癌","瘤","结石","囊肿","增生","钙化","硬化","异位","梗塞","血栓","积水","腹水","畸形","占位","肿物","团块","结节"]
            # 超声描述词也可作为疾病证据（如"强回声团"→结石）
            evidence_extras = ["强回声","无声影","声影","光团","光带","回声团","暗区","无回声","混合回声","低回声","稍高回声"]
            entry = _template_index.get(name, {})
            is_abnormal = any(kw in keyword for kw in abnormal_kw)
            extra_bonus = 0
            if is_abnormal:
                # 检查文本中是否有匹配的疾病关键词或超声描述证据
                has_evidence = any(kw in text for kw in abnormal_kw + evidence_extras)
                if has_evidence:
                    extra_bonus = 20  # 有证据加成
                else:
                    extra_bonus = -50  # 无证据强扣分
            scored[name] = max(scored.get(name, 0), 100 + len(keyword) * 5 + extra_bonus)

        # P0-2.5: 文本级异常信号检测 — 文本有"结节/回声/占位"等描述时, 对应疾病模板加分
    # 注意: "强回声"在"胆囊"文本中出现时不应加分给"肝内钙化灶"
    _text_abnormal_signals = ["结节","无回声","低回声","混合回声","稍高回声","强回声","回声团","囊性","囊肿","水泡","水囊"]
    _text_has_abnormal = any(sig in text for sig in _text_abnormal_signals)
    if _text_has_abnormal:
        for name, entry in _template_index.items():
            if _valid_names and name not in _valid_names: continue
            tpl_text = entry.get("name","") + entry.get("info1","")[:200]
            # 限制: 异常信号加分必须同时有共享受益的器官词
            _matched = False
            for sig in _text_abnormal_signals:
                if sig in text and sig in tpl_text:
                    for organ in _ORGAN_WORDS:
                        if organ in text and organ in tpl_text:
                            scored[name] = max(scored.get(name, 0), 140)
                            _matched = True
                            break
                    if _matched:
                        break
        # 同器官的正常模板扣分(文本有异常信号时正常模板不配同分)
        for name, entry in _template_index.items():
            if _valid_names and name not in _valid_names: continue
            if "正常" in name or "未见异常" in name:
                for organ in _ORGAN_WORDS:
                    if organ in text and organ in (entry.get("info1","") + entry.get("name","")):
                        scored[name] = max(scored.get(name, 0) - 80, 60)
                        break
        # 疾病模板加分: 同器官时疾病模板额外加分(超过正常模板)
        for name, entry in _template_index.items():
            if _valid_names and name not in _valid_names: continue
            if "正常" not in name and "未见异常" not in name:
                tpl_text = entry.get("name","") + entry.get("info1","")[:200]
                for organ in _ORGAN_WORDS:
                    if organ in text and organ in tpl_text:
                        # 文本和模板都有异常信号词 → +20
                        for sig in _text_abnormal_signals:
                            if sig in text or sig in tpl_text:
                                scored[name] = max(scored.get(name, 0), 120) + 20
                                break
                        break

    # P0-2.6: 文本有异常信号时, 正常模板不再享受P0-3加分
    _suppress_normal = any(kw in text for kw in ["已切除","切除","未探及","未扪及","术后","切除术后","全切"]) or _text_has_abnormal

    # P0-3: "正常"关键词匹配——文本含"正常"时给正常模板加成
    normal_words = ["正常", "大小正常", "光滑", "光整", "规则", "均匀", "清晰", "通畅"]
    has_normal_signal = any(w in text for w in normal_words) and not _suppress_normal
    if has_normal_signal:
        for name, entry in _template_index.items():
            if _valid_names and name not in _valid_names: continue
            if "正常" in name and any(w in text for w in ["正常","大小正常","光滑"]):
                scored[name] = max(scored.get(name, 0), 120)
            # 文本含器官词且模板名含"正常"时保底加分
            if "正常" in name:
                for organ in _ORGAN_WORDS:
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

        # 策略1.5: 模板匹配关键词精确匹配 (固定规则)
    match_kw_dict = {
        "结石":["结石","强回声伴声影"],
        "肾结石":["肾","结石","强回声伴声影","肾盂"],
        "囊肿":["囊肿","囊性","无回声"],
        "子宫肌瘤":["子宫","肌瘤","低回声","肌层"],
        "胆囊结石":["胆囊","结石","强回声伴声影","随体位"],
        "脂肪肝":["脂肪肝","回声增粗","回声增强","肝肾反差"],
        "前列腺增生":["前列腺增生","突入膀胱","残余尿"],
        "甲状腺结节":["甲状腺","低回声","结节","TI-RADS","边界","实性"],
        "乳腺结节":["乳腺","结节","BI-RADS","低回声","边界","CDFI","血流"],
        "肝囊肿":["肝","囊肿","无回声","边界清","后方增强"],
        "胆囊息肉":["胆囊","息肉","附壁","不移动"],
        "正常心脏":["心脏","室壁","瓣膜","室间隔","心包","未见异常","运动正常"],
        "正常乳腺":["乳腺","未见异常","腺体层","未见结节","导管","腋窝","BI-RADS"],
        "正常甲状腺":["甲状腺","峡部","腺体","未见结节","血流分布","未见异常","腺体内"],
        "正常妇科":["子宫","内膜","卵巢","宫颈","盆腔","宫腔","附件","未见异常"],
        "腹部正常":["肝","胆囊","胰腺","脾脏","未见异常","正常","未见结石","未见占位"],
        "早孕":["早孕","孕囊","胚芽","卵黄囊","心管搏动","胎心"],
        "中孕":["中孕","双顶径","股骨长","头围","腹围","羊水","胎盘"],
        "肝内钙化灶":["肝","钙化灶","强回声","声影"],
        "胆囊炎":["胆囊","壁毛糙","壁增厚"],
        "前列腺钙化灶":["前列腺","钙化"],
        "子宫内膜声像改变":["子宫内膜","内膜","回声欠均匀"],
    }
    if match_kw_dict:
        for tpl_name, keywords in match_kw_dict.items():
            if tpl_name not in _template_index:
                continue
            if _valid_names and tpl_name not in _valid_names:
                continue
            for kw in keywords:
                if kw in text and len(kw) >= 2:
                    scored[tpl_name] = max(scored.get(tpl_name, 0), 200)
                    break

    # 策略2: 器官词匹配INFO1 (复用_ORGAN_WORDS)
    for name, entry in _template_index.items():
        if _valid_names and name not in _valid_names: continue
        info1 = entry.get("info1", "")
        for organ in _ORGAN_WORDS:
            if organ in text and organ in info1:
                scored[name] = scored.get(name, 0) + 20
                break

    # 策略3: 疾病词匹配 (硬编码)
    disease_words = ["结石","囊肿","肌瘤","息肉","增生","钙化","血管瘤","脂肪肝","结节","积液","占位","弥漫","斑块","狭窄","血栓","积水","腹水","脾大","肝硬化","畸胎瘤","腺肌症"]
    for name, entry in _template_index.items():
        if _valid_names and name not in _valid_names: continue
        info1 = entry.get("info1", "") + entry.get("info2", "")
        for disease in disease_words:
            if disease in text and disease in info1:
                scored[name] = scored.get(name, 0) + 15
                break

    # 策略4: 检查类型模糊匹配模块名 (硬编码)
    module_map = {"产科":["产科"],"胎儿":["产科"],"孕":["产科"],"心脏":["心脏","心脏血管"],"心超":["心脏"],
        "心包":["心脏"],"瓣":["心脏"],"甲状腺":["甲状腺"],"乳腺":["甲状腺","乳腺"],
        "血管":["周围血管"],"颈动脉":["周围血管"],"动脉":["周围血管"],"TCD":["TCI"],
        "腹部":["UIS","肝脏","胰腺","脾脏","肾脏"],"肝胆":["UIS","肝脏"],
        "妇科":["子宫","UIS","附件"],"子宫":["子宫"],"卵巢":["子宫","附件"],
        "泌尿":["泌尿生殖系","肾脏"],"前列腺":["肾脏"],"膀胱":["肾脏"],
        "睾丸":["男生殖系"],"附睾":["男生殖系"],"肺":["胸部"],"胸":["胸部"]}
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
        "胰腺": ["胰腺","胰头","胰体","胰尾","主胰管"],
        "脾脏": ["脾脏","脾门","脾实"],
    }
    # P0-4: 否定信号守卫——ASR有"已切除/术后/未探及/未扪及/未见"时, 疾病模板扣分
    _SUPPRESS_WORDS = ["切除","已切除","术后","全切","未探及","未扪及","未见积水","未见结石","未见占位","未见结节","未见异常"]
    _has_suppression = any(w in text for w in _SUPPRESS_WORDS)
    # 补充: "未见XX"否定检测
    _has_negation_signal = bool(re.search(r'未见[^。，；]{1,12}', text))
    # 确定文本属于哪个器官类别
    text_organ_categories = set()
    for cat, organs in organ_module_map.items():
        if any(o in text for o in organs):
            text_organ_categories.add(cat)

    for name in list(_template_index.keys()):
        if _valid_names and name not in _valid_names: continue
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
            # P0-4: 否定词守卫——文本有"已切除"但模板是"正常" → 强扣分
            if _has_suppression and "正常" in name:
                scored[name] = max(scored.get(name, 0) - 120, 0)
            # 更严格的守卫: 如果模板INFO1中没有任何文本中的器官词 → 强扣分
            # 注意: text中有"双肾"但organ_words是"肾脏", 需额外检查"肾"
            tpl_has_text_organ = any(o in tpl_text for o in _ORGAN_WORDS)
            # 补充检查: text中的"肾"类词（双肾/左肾/右肾/肾实质）在模板中是否存在
            if not tpl_has_text_organ:
                kidney_variants = ["双肾", "左肾", "右肾", "实质回声", "集合"]
                if any(v in text for v in kidney_variants) and any(v in tpl_text for v in kidney_variants):
                    tpl_has_text_organ = True
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
            has_organ = any(o in (entry.get("info1","") + entry.get("name","")) for o in _ORGAN_WORDS)
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
