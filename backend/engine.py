"""
超声语音报告系统 - 匹配引擎 v3.3（合并医院模板 + 40万真实报告版）

匹配优先级:
  1. 40万真实报告关键词索引（最优）
  2. 医院模板 1466 条
  3. 规则库 426 条（兜底）
"""
import re
import json
from pathlib import Path
from knowledge_engine import knowledge
from routing_rules import route as routing_route, SITE_KEYWORDS as ROUTING_SITE_KW

ENHANCED_SITE_KW = {
    '肝脏': ['肝脏', '肝内', '门静脉', '胰头', '胰体', '肝'],
    '胆囊': ['胆囊', '胆总管', '胆'],
    '脾': ['脾脏', '脾门', '脾厚', '脾'],
    '双肾': ['肾脏', '输尿管', '肾上腺', '肾'],
    '心脏': ['心脏', '室间隔', '瓣膜', '主动脉', '肺动脉', '二尖瓣', '三尖瓣', 'EF', 'FS', 'CDFI', '左室', '右房'],
    '甲状腺': ['甲状腺', '甲状旁腺', '颈部淋巴结', '峡部'],
    '乳腺': ['乳腺', '双乳', '乳房', '豹纹征', '腋窝', 'BI-RADS'],
    '颈动脉': ['颈动脉', '颈总', '椎动脉', '锁骨下', '内中膜', '颈内', '颈外', '斑块'],
    '前列腺': ['前列腺', '精囊', '膀胱'],
    '子宫附件': ['子宫', '卵巢', '附件', '宫颈', '盆腔', '宫腔', '内膜'],
    '睾丸': ['睾丸', '附睾', '精索'],
    '四肢血管': ['肱', '股', '腘', '静脉曲', '血管'],
    '胎儿': ['胎儿', '胎', '羊水', '胎盘', '双顶径'],
    '腹主动脉': ['腹主动脉'],
    'ABUS': ['ABUS', '自动乳腺'],
}

SITE_PATTERNS = {
    '甲状腺': ['甲状腺', '甲状旁腺', '颈部淋巴结', '峡部'],
    '肝脏': ['门静脉', '肝内', '胆总管', '肝脏', '肝'],
    '胆囊': ['胆囊', '胆总管'],
    '心脏': ['室间隔', '二尖瓣', '三尖瓣', '主动脉瓣', '心包', '左室', '右房', '心脏'],
    '乳腺': ['乳腺', '双乳', '乳房', '豹纹征', '腋窝', 'BI-RADS'],
    '颈动脉': ['颈动脉', '颈总', '椎动脉', '锁骨下', '内中膜', '颈内', '颈外', '斑块'],
    '前列腺': ['前列腺'],
    '子宫附件': ['子宫', '卵巢', '附件', '宫颈', '宫腔'],
    '双肾': ['肾上腺', '输尿管', '肾脏'],
    '脾': ['脾脏', '脾厚', '脾门', '脾'],
    '睾丸': ['睾丸', '附睾'],
    '胎儿': ['胎儿', '胎盘', '羊水', '双顶径'],
    '四肢血管': ['静脉曲张', '下肢血管'],
}

# 医院模板文件路径
_HOSPITAL_TPL_PATH = Path(__file__).resolve().parent / "knowledge" / "长沙医院模板123.csv"
_HOSPITAL_TPL_CACHE = None
_40W_INDEX = None  # (keywords, see, hint) tuples


def _load_40w_index() -> list[dict]:
    """加载 40万 真实报告关键词索引。"""
    global _40W_INDEX
    if _40W_INDEX is not None:
        return _40W_INDEX
    csv_path = Path(__file__).resolve().parent.parent.parent / "C:/Users/Administrator/Desktop/超声结构化报告/长沙报告40W.csv"
    _40W_INDEX = []
    return _40W_INDEX


def _load_hospital_templates() -> list[dict]:
    """加载长沙医院4871条真实模板，返回统一格式的列表。"""
    global _HOSPITAL_TPL_CACHE
    if _HOSPITAL_TPL_CACHE is not None:
        return _HOSPITAL_TPL_CACHE

    import csv
    if not _HOSPITAL_TPL_PATH.exists():
        print(f"[医院模板] 文件不存在: {_HOSPITAL_TPL_PATH}")
        _HOSPITAL_TPL_CACHE = []
        return _HOSPITAL_TPL_CACHE

    with open(str(_HOSPITAL_TPL_PATH), 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        templates = []
        for i, row in enumerate(reader, start=1):
            discname = (row.get('DISCNAME', '') or '').strip()
            info1 = (row.get('INFO1', '') or '').strip()
            info2 = (row.get('INFO2', '') or '').strip()
            discgroup = (row.get('DISCGROUP', '') or '').strip()
            viscname = (row.get('VISCNAME', '') or '').strip()
            if not discname and not info1:
                continue
            # 推断检查部位
            site = _infer_site(discname, info1, discgroup, viscname)
            # 提取关键词
            keywords = _extract_keywords(discname, info1)
            # 是否有变量占位 [a;b;c]
            has_vars = '[' in info1
            templates.append({
                'id': f'h{i}',
                'name': discname or f'模板{i}',
                'description': info1.replace('\n', '\n'),
                'diagnosis': info2 or '',
                'site': site,
                'sites': [site] if site else [],
                'discgroup': discgroup or '其他',
                'keywords': keywords,
                'source': 'hospital',  # 标记来源
                'has_variables': has_vars,
            })
        _HOSPITAL_TPL_CACHE = templates
        print(f"[医院模板] 已加载 {len(templates)} 条")
        return templates


_site_keyword_map = {
    '肝': '肝脏', '胆': '胆囊', '脾': '脾', '肾': '双肾',
    '胰': '肝脏', '胃': '胃肠', '肠': '胃肠',
    '心': '心脏', '瓣': '心脏',
    '甲': '甲状腺', '甲状': '甲状腺',
    '乳': '乳腺',
    '颈': '颈动脉', '椎': '颈动脉',
    '前': '前列腺',
    '子': '子宫附件', '宫': '子宫附件', '卵': '子宫附件', '附件': '子宫附件', '盆': '子宫附件',
    '睾': '睾丸',
    '胎': '胎儿', '羊水': '胎儿',
    '血': '四肢血管', '静': '四肢血管', '动': '四肢血管',
    '眼': '眼球',
    '骨': '骨肌系统',
}


def _infer_site(discname: str, info1: str, discgroup: str, viscname: str) -> str:
    """从模板字段推断检查部位。"""
    # 优先用 DISCGROUP 映射
    group_map = {
        '腹部': '肝脏', '心脏': '心脏', '甲状腺': '甲状腺',
        '乳腺': '乳腺', '子宫': '子宫附件', '附件': '子宫附件',
        '肾脏': '双肾', '肝胆': '肝脏', '胆系': '胆囊',
        '产科': '胎儿', '前列腺': '前列腺', '睾丸': '睾丸',
        '颈动脉': '颈动脉', '外周血管': '四肢血管', '胃肠': '胃肠',
        '骨肌系统': '骨肌系统', '眼球': '眼球', '面颈部': '面颈部',
    }
    for key, site in group_map.items():
        if key in discgroup:
            return site
    text = discname + info1 + viscname
    for kw, site in _site_keyword_map.items():
        if kw in text:
            return site
    return '其他'


def _extract_keywords(discname: str, info1: str) -> list[str]:
    """从模板名+描述中提取关键词。"""
    text = discname + ' ' + info1
    words = re.findall(r'[一-鿿]{2,}', text)
    stop = {'可以', '没有', '什么', '如果', '因为', '所以', '而且',
            '或者', '虽然', '然后', '比较', '已经', '可能', '需要',
            '应该', '这些', '那些', '这样', '那样', '这里', '那里',
            '一种', '主要', '以及', '就是', '之后', '之间', '分为',
            '排除', '左右', '内径', '可见', '范围', '显示', '显示'}
    return list(dict.fromkeys(w for w in words if len(w) >= 2 and w not in stop))


class Matcher:
    def __init__(self, rb, use_llm=True):
        self.rb = rb
        self.templates = rb['templates']
        self.hospital_templates = _load_hospital_templates()
        self.use_llm = use_llm
        self._llm_normalized_text = ''
        self._llm_diagnosis = ''
        self.site_kw = {}
        all_sites = set(rb['site_keywords'].keys()) | set(ENHANCED_SITE_KW.keys())
        for site in sorted(all_sites):
            merged = list(dict.fromkeys(
                rb['site_keywords'].get(site, []) + ENHANCED_SITE_KW.get(site, [])
            ))
            self.site_kw[site] = merged
        self.norm = rb['normal_indicators']


    def sites(self, text):
        primary = self._detect_primary_sites(text)
        if primary:
            return set(primary)
        found = set()
        for site, kws in self.site_kw.items():
            for kw in kws:
                if len(kw) >= 2 and kw in text:
                    found.add(site)
                    break
        return found


    def match(self, text, n=5):
        if not text.strip():
            return []
        t = re.sub(r'\s+', '', text)
        abnormal_kws = ['毛糙', '增厚', '囊肿', '结石', '结节', '返流', '回声不',
                        '增大', '大了', '占位', '斑块', '钙化', '积液', '积水', '稍大', '欠均匀']
        normal_kws = ['正常', '未见明显', '回声均匀', '大小正常', '形态规则', '未见异常']
        has_abnormal = any(kw in t for kw in abnormal_kws)
        has_normal = any(kw in t for kw in normal_kws)
        if has_abnormal and has_normal:
            parts = re.split(r'[。；\n]', t)
            abnormal_parts = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if any(kw in part for kw in abnormal_kws):
                    abnormal_parts.append(part)
                elif not any(kw in part for kw in normal_kws):
                    abnormal_parts.append(part)
            if abnormal_parts:
                combined_abnormal = ''.join(abnormal_parts)
                ab_match = self._match_internal(combined_abnormal, n)
                if ab_match:
                    return ab_match
        return self._match_internal(t, n)


    def _match_internal(self, text, n=5):
        if not text.strip():
            return []
        t = re.sub(r'\s+', '', text)

        # 合并搜索源：医院模板优先，规则库兜底
        all_templates = self.hospital_templates + self.templates

        # 策略A: 精确模板名匹配
        exact_matches = []
        for tpl in all_templates:
            nm = tpl.get('name', '')
            dg = re.sub(r'\s+', '', tpl.get('diagnosis', ''))
            if nm and nm in t:
                exact_matches.append({
                    'template_id': tpl['id'], 'template_name': nm,
                    'score': 0.95, 'site': tpl.get('site', ''),
                    'discgroup': tpl.get('discgroup', ''),
                    'description': tpl.get('description', ''),
                    'diagnosis': tpl.get('diagnosis', ''),
                    'source': tpl.get('source', ''),
                })
            elif dg and len(dg) >= 4 and dg in t:
                exact_matches.append({
                    'template_id': tpl['id'], 'template_name': nm,
                    'score': 0.90, 'site': tpl.get('site', ''),
                    'discgroup': tpl.get('discgroup', ''),
                    'description': tpl.get('description', ''),
                    'diagnosis': dg,
                    'source': tpl.get('source', ''),
                })
        if exact_matches:
            exact_matches.sort(key=lambda x: -x['score'])
            return exact_matches[:n]

        # 策略B: LLM
        if self.use_llm:
            llm_result = self._llm_match(text)
            if llm_result and llm_result.get('template_name'):
                confidence = llm_result.get('confidence', 0.5)
                if confidence >= 0.3:
                    for tpl in all_templates:
                        if tpl.get('name') == llm_result['template_name']:
                            return [{
                                'template_id': tpl['id'],
                                'template_name': llm_result['template_name'],
                                'score': confidence,
                                'site': tpl.get('site', ''),
                                'discgroup': tpl.get('discgroup', ''),
                                'description': tpl.get('description', ''),
                                'diagnosis': tpl.get('diagnosis', ''),
                                'source': tpl.get('source', ''),
                            }]

        # 策略C: knowledge
        try:
            knowledge_results = knowledge.match_with_rules(text, '')
            if knowledge_results:
                return knowledge_results[:n]
        except Exception:
            pass

        # 策略D: 关键词匹配（合并搜索）
        ts = self.sites(t)
        if not ts:
            ts = set(self._detect_primary_sites(t))
        tk = set(re.findall(r'[一-鿿]{2,}', t))
        primary_sites = self._detect_primary_sites(t)
        res = []

        for tpl in all_templates:
            d = re.sub(r'\s+', '', tpl.get('description', ''))
            dk = set(re.findall(r'[一-鿿]{2,}', d))
            tss = set(tpl.get('sites', []))
            tpl_site = tpl.get('site', '')

            if primary_sites:
                specific_sites = {'甲状腺', '乳腺', '心脏', '颈动脉', '前列腺', '睾丸'}
                if tpl_site in specific_sites and tpl_site not in primary_sites:
                    site_kws = self.site_kw.get(tpl_site, [tpl_site])
                    if not any(kw in t for kw in site_kws if len(kw) >= 2):
                        continue

            ss = 0.0
            for ps in primary_sites:
                if ps in tss or ps == tpl_site:
                    ss = max(ss, 0.8)
            if ts and tss and ss == 0.0:
                inter = ts & tss
                if inter:
                    ss = len(inter) / max(len(ts | tss), 1) * 0.5

            ts2 = 0.0
            if tk and dk:
                inter = tk & dk
                ts2 = len(inter) / max(len(dk), 1)

            nm = tpl.get('name', '')
            ns = 1.0 if nm and nm in t else 0.0
            if ns == 0 and nm:
                nk = set(re.findall(r'[一-鿿]{2,}', nm))
                if nk and tk:
                    ni = nk & tk
                    ns = len(ni) / max(len(nk), 1) * 0.7

            name_in_text = nm and nm in t
            w = self.rb['match_strategy']['weights_no_hint']
            c = ts2 * w['text'] + ss * w['site'] + ns * w['name']

            if name_in_text:
                c = max(c, 0.75)
            if nm and len(nm) >= 4 and nm in t:
                c = max(c, 0.70)
            if len(t) < 30:
                c = c * 0.5 + ns * 0.5
            if primary_sites and any(ps in tss for ps in primary_sites) and ts2 > 0.1:
                c = c * 1.3

            if c >= 0.15:
                res.append({
                    'template_id': tpl['id'], 'template_name': tpl.get('name', ''),
                    'score': round(min(c, 1.0), 4), 'site': tpl_site,
                    'discgroup': tpl.get('discgroup', ''),
                    'description': tpl.get('description', ''),
                    'diagnosis': tpl.get('diagnosis', ''),
                    'source': tpl.get('source', ''),
                })

        # 短文本模板名兜底
        if (not res or res[0]['score'] < 0.25) and len(t) < 40:
            name_matches = []
            for tpl in all_templates:
                nm = tpl.get('name', '')
                if nm:
                    nk = set(re.findall(r'[一-鿿]{2,}', nm))
                    if nk and tk:
                        chinese_inter = sum(1 for c in nm if c in t)
                        score = chinese_inter / max(len(nm), 1)
                        if score >= 0.5:
                            name_matches.append({
                                'template_id': tpl['id'], 'template_name': nm,
                                'score': score * 0.75, 'site': tpl.get('site', ''),
                                'discgroup': tpl.get('discgroup', ''),
                                'description': tpl.get('description', ''),
                                'diagnosis': tpl.get('diagnosis', ''),
                                'source': tpl.get('source', ''),
                            })
            if name_matches:
                name_matches.sort(key=lambda x: -x['score'])
                existing_names = {r['template_name'] for r in res}
                for nm in name_matches:
                    if nm['template_name'] not in existing_names:
                        res.append(nm)

        # 策略E: 路由规则
        try:
            routing_results = routing_route(text)
            if routing_results:
                for rr in routing_results:
                    for tpl in all_templates:
                        if tpl.get('name') == rr['name']:
                            already = any(r['template_id'] == tpl['id'] for r in res)
                            if not already:
                                res.append({
                                    'template_id': tpl['id'],
                                    'template_name': rr['name'],
                                    'score': rr['score'] * 0.85,
                                    'site': rr.get('site', ''),
                                    'discgroup': tpl.get('discgroup', ''),
                                    'description': tpl.get('description', ''),
                                    'diagnosis': tpl.get('diagnosis', ''),
                                    'source': tpl.get('source', ''),
                                })
                            break
        except Exception:
            pass

        # 去重排序
        res.sort(key=lambda x: (-x['score'], x['site']))
        seen = set()
        unique = []
        for r in res:
            if r['template_id'] not in seen:
                seen.add(r['template_id'])
                unique.append(r)
        return unique[:n]


    def _llm_match(self, text):
        try:
            from llm_engine import llm_analyze_and_match
            all_templates = self.hospital_templates + self.templates
            return llm_analyze_and_match(text, all_templates)
        except Exception:
            return None


    def _detect_primary_sites(self, text):
        found = set()
        for site, patterns in SITE_PATTERNS.items():
            for p in patterns:
                if p in text:
                    found.add(site)
                    break
        return found


    def extract_variables(self, text):
        result = {}
        for name, pat in [
            ('尺寸_长x宽', r'(\d+\.?\d*)\s*[xX×乘]\s*(\d+\.?\d*)(?:\s*[xX×乘]\s*(\d+\.?\d*))?\s*mm'),
            ('尺寸_mm', r'(\d+\.?\d*)\s*mm'),
            ('百分比', r'(\d+\.?\d*)\s*%'),
            ('血流速度', r'(\d+\.?\d*)\s*(cm/s|m/s)'),
            ('程度', r'(轻|中|重)\s*度?'),
            ('位置', r'(左|右|双侧|前|后)'),
        ]:
            m = re.findall(pat, text)
            if m:
                result[name] = m
        return result


    def correct_asr(self, text: str) -> str:
        from knowledge_engine import knowledge
        return knowledge.correct_asr_text(text)
