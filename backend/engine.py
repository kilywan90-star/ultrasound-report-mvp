"""
超声语音报告系统 - 匹配引擎 v3.1（修复版）
修复：关键词重叠冲突、短字符误匹配、部位识别不全、长文本分段
"""
import re, json
from knowledge_engine import knowledge
from routing_rules import route as routing_route, SITE_KEYWORDS as ROUTING_SITE_KW

# 路由规则中的site_keywords更完整，覆盖规则库不足
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

# 专有部位名称映射 — primary_sites检测用
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


class Matcher:
    def __init__(self, rb, use_llm=True):
        self.rb = rb
        self.templates = rb['templates']
        self.use_llm = use_llm
        self._llm_normalized_text = ''
        self._llm_diagnosis = ''
        # 合并规则库 + 增强keywords
        self.site_kw = {}
        all_sites = set(rb['site_keywords'].keys()) | set(ENHANCED_SITE_KW.keys())
        for site in sorted(all_sites):
            merged = list(dict.fromkeys(
                rb['site_keywords'].get(site, []) + ENHANCED_SITE_KW.get(site, [])
            ))
            self.site_kw[site] = merged
        self.norm = rb['normal_indicators']

    def sites(self, text):
        """用primary_sites精准检测，避免短词冲突"""
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
        if not text.strip(): return []
        t = re.sub(r'\s+', '', text)

        # 混合描述智能分段
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
                if not part: continue
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
        if not text.strip(): return []
        t = re.sub(r'\s+', '', text)

        # 策略A: 精确模板名或诊断名匹配
        exact_matches = []
        for tpl in self.templates:
            nm = tpl.get('name', '')
            dg = re.sub(r'\s+', '', tpl.get('diagnosis', ''))
            if nm and nm in t:
                exact_matches.append({
                    'template_id': tpl['id'], 'template_name': nm,
                    'score': 0.95, 'site': tpl['site'],
                    'discgroup': tpl.get('discgroup', ''),
                    'description': tpl.get('description', ''),
                    'diagnosis': tpl.get('diagnosis', ''),
                })
            elif dg and len(dg) >= 4 and dg in t:
                exact_matches.append({
                    'template_id': tpl['id'], 'template_name': nm,
                    'score': 0.90, 'site': tpl['site'],
                    'discgroup': tpl.get('discgroup', ''),
                    'description': tpl.get('description', ''),
                    'diagnosis': dg,
                })
        if exact_matches:
            exact_matches.sort(key=lambda x: -x['score'])
            return exact_matches[:n]

        # 策略B: LLM语义匹配（对乱序/混淆文本有效，也对描述有异常但关键词匹配到正常模板的情况有效）
        if self.use_llm:
            llm_result = self._llm_match(text)
            if llm_result and llm_result.get('template_name'):
                tpl_name = llm_result['template_name']
                confidence = llm_result.get('confidence', 0.5)
                if confidence >= 0.3:
                    for tpl in self.templates:
                        if tpl.get('name') == tpl_name:
                            return [{
                                'template_id': tpl['id'],
                                'template_name': tpl_name,
                                'score': confidence,
                                'site': tpl.get('site', ''),
                                'discgroup': tpl.get('discgroup', ''),
                                'description': tpl.get('description', ''),
                                'diagnosis': tpl.get('diagnosis', ''),
                            }]

        # 策略C: knowledge 规则库匹配
        try:
            knowledge_results = knowledge.match_with_rules(text, '')
            if knowledge_results:
                return knowledge_results[:n]
        except:
            pass

        # 策略C: 增强关键词匹配
        ts = self.sites(t)
        if not ts:
            ts = set(self._detect_primary_sites(t))
        tk = set(re.findall(r'[一-鿿]{2,}', t))
        primary_sites = self._detect_primary_sites(t)

        res = []
        for tpl in self.templates:
            d = re.sub(r'\s+', '', tpl.get('description', ''))
            dk = set(re.findall(r'[一-鿿]{2,}', d))

            tss = set(tpl.get('sites', []))
            tpl_site = tpl.get('site', '')

            # 当检测到明确的部位时，过滤明显不匹配的模板
            # 规则: 模板site是专有部位名(非"腹部"等通用)且不在primary_sites中 → 跳过
            if primary_sites:
                # 定义"专有部位" — 这些site不会出现在其他部位的文本中
                specific_sites = {'甲状腺', '乳腺', '心脏', '颈动脉', '前列腺', '睾丸'}
                if tpl_site in specific_sites and tpl_site not in primary_sites:
                    # 检查是否是乳腺的"豹纹征"但匹配了甲状腺模板
                    # 只有当文本中完全没有该部位关键词时才跳过
                    site_kws = self.site_kw.get(tpl_site, [tpl_site])
                    if not any(kw in t for kw in site_kws if len(kw) >= 2):
                        continue

            # 部位匹配度分
            ss = 0.0
            for ps in primary_sites:
                if ps in tss or ps == tpl_site:
                    ss = max(ss, 0.8)
            if ts and tss and ss == 0.0:
                inter = ts & tss
                if inter:
                    ss = len(inter) / max(len(ts | tss), 1) * 0.5

            # 文本关键词重叠度
            ts2 = 0.0
            if tk and dk:
                inter = tk & dk
                ts2 = len(inter) / max(len(dk), 1)

            # 模板名匹配
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
                    'template_id': tpl['id'], 'template_name': tpl['name'],
                    'score': round(min(c, 1.0), 4), 'site': tpl['site'],
                    'discgroup': tpl.get('discgroup', ''),
                    'description': tpl.get('description', ''),
                    'diagnosis': tpl.get('diagnosis', ''),
                })

        # 策略D: 短文本模板名fallback
        if (not res or res[0]['score'] < 0.25) and len(t) < 40:
            name_matches = []
            for tpl in self.templates:
                nm = tpl.get('name', '')
                if nm:
                    nk = set(re.findall(r'[一-鿿]{2,}', nm))
                    if nk and tk:
                        chinese_inter = sum(1 for c in nm if c in t)
                        score = chinese_inter / max(len(nm), 1)
                        if score >= 0.5:
                            name_matches.append({
                                'template_id': tpl['id'], 'template_name': nm,
                                'score': score * 0.75, 'site': tpl['site'],
                                'discgroup': tpl.get('discgroup', ''),
                                'description': tpl.get('description', ''),
                                'diagnosis': tpl.get('diagnosis', ''),
                            })
            if name_matches:
                name_matches.sort(key=lambda x: -x['score'])
                existing_names = {r['template_name'] for r in res}
                for nm in name_matches:
                    if nm['template_name'] not in existing_names:
                        res.append(nm)

        # 策略E: 路由规则补充
        routing_results = routing_route(text)
        if routing_results:
            for rr in routing_results:
                for tpl in self.templates:
                    if tpl.get('name') == rr['name']:
                        already = any(r['template_id'] == tpl['id'] for r in res)
                        if not already:
                            res.append({
                                'template_id': tpl['id'],
                                'template_name': rr['name'],
                                'score': rr['score'] * 0.85,
                                'site': rr['site'],
                                'discgroup': tpl.get('discgroup', ''),
                                'description': tpl.get('description', ''),
                                'diagnosis': tpl.get('diagnosis', ''),
                            })
                        break

        res.sort(key=lambda x: (-x['score'], x['site']))
        seen = set()
        unique = []
        for r in res:
            if r['template_id'] not in seen:
                seen.add(r['template_id'])
                unique.append(r)
        return unique[:n]

    def _llm_match(self, text):
        """LLM语义匹配+诊断：1次API调用完成规范化+匹配+诊断"""
        try:
            from llm_engine import llm_analyze_and_match

            # 快速关键词评分构建候选（不需要额外API）
            ts = self.sites(text)
            text_kws = set(re.findall(r'[一-鿿]{2,}', text))
            scored = []
            for tpl in self.templates:
                nm = tpl.get('name', '')
                nm_kws = set(re.findall(r'[一-鿿]{2,}', nm.replace('（', '').replace('）', '')))
                nm_score = len(nm_kws & text_kws) / max(len(nm_kws), 1) if nm_kws else 0
                tss = set(tpl.get('sites', []))
                site_score = 0
                if ts and tss:
                    inter = ts & tss
                    site_score = len(inter) / max(len(ts | tss), 1)
                total = nm_score + site_score
                if total > 0.1:
                    scored.append((total, tpl))
            scored.sort(key=lambda x: -x[0])
            candidates = [t[1] for t in scored[:30]]

            if candidates:
                result = llm_analyze_and_match(text, candidates)
                if result and result.get('confidence', 0) >= 0.4 and result.get('template_name', ''):
                    self._llm_normalized_text = result.get('normalized_text', '')
                    self._llm_diagnosis = result.get('diagnosis', '')
                    return result
        except Exception as e:
            pass
        return None

    def _detect_primary_sites(self, text):
        """检测主要检查部位 — 用≥3字的特定关键词避免误匹配"""
        t = re.sub(r'\s+', '', text)
        found = []
        for site, patterns in SITE_PATTERNS.items():
            for pat in patterns:
                if pat in t:
                    found.append(site)
                    break

        # 过滤 "内中膜" 不应匹配 子宫附件
        if '子宫附件' in found:
            t_clean = t.replace('内中膜', '')
            if '内膜' not in t_clean:
                found.remove('子宫附件')

        if len(found) > 1:
            specific_sites = set()
            for site in found:
                patterns = SITE_PATTERNS.get(site, [])
                specific = [p for p in patterns if len(p) >= 3]
                if any(p in t for p in specific):
                    specific_sites.add(site)
            if specific_sites:
                return list(specific_sites)

        return found

    def extract_variables(self, text):
        result = {}
        vr = self.rb.get('variable_rules', {})
        for var_name, rule in vr.items():
            matches = re.findall(rule['pattern'], text, re.IGNORECASE)
            if matches:
                result[var_name] = [list(m) if isinstance(m, tuple) else m for m in matches]
        return result

    def correct_asr(self, text: str) -> str:
        return knowledge.correct_asr_text(text)
