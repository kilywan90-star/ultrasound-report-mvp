"""
超声语音报告系统 - 匹配引擎（集成knowledge规则库 + 路由规则）
"""
import re, json
from knowledge_engine import knowledge
from routing_rules import route as routing_route


class Matcher:
    def __init__(self, rb):
        self.rb = rb
        self.templates = rb['templates']
        self.site_kw = rb['site_keywords']
        self.norm = rb['normal_indicators']

    def sites(self, text):
        found = set()
        for site, kws in self.site_kw.items():
            for kw in kws:
                if kw in text: found.add(site); break
        return found

    def match(self, text, n=5):
        if not text.strip(): return []
        t = re.sub(r'\s+', '', text)

        # === 策略0: 混合描述智能分段 → 优先异常段匹配 ===
        # 检测是否是"既有正常又有异常"的混合描述
        abnormal_kws = ['不正常','毛糙','增厚','囊肿','结石','结节','返流','回声不',
                        '增大','大了','占位','斑块','钙化','积液','积水','稍大','欠均匀']
        normal_kws = ['正常','未见明显','回声均匀','大小正常','形态规则','未见异常']

        has_abnormal = any(kw in t for kw in abnormal_kws)
        has_normal = any(kw in t for kw in normal_kws)

        if has_abnormal and has_normal:
            # 按标点分割段落
            parts = re.split(r'[。；\n]', t)
            normal_parts = []
            abnormal_parts = []
            for part in parts:
                part = part.strip()
                if not part: continue
                # 判断这段是正常还是异常
                if any(kw in part for kw in abnormal_kws):
                    abnormal_parts.append(part)
                elif any(kw in part for kw in normal_kws):
                    normal_parts.append(part)
                else:
                    # 既无明显正常也无明显异常，加入异常候选
                    abnormal_parts.append(part)

            # 优先用异常段匹配
            if abnormal_parts:
                combined_abnormal = ''.join(abnormal_parts)
                ab_match = self._match_internal(combined_abnormal, n)
                if ab_match:
                    return ab_match

            # 如果异常段没匹配到，回退到全量匹配
            if normal_parts and not abnormal_parts:
                combined_normal = ''.join(normal_parts)
                nm_match = self._match_internal(combined_normal, n)
                if nm_match:
                    return nm_match

        return self._match_internal(t, n)

    def _match_internal(self, text, n=5):
        """内部匹配逻辑（原match的主体）"""
        if not text.strip(): return []
        t = re.sub(r'\s+', '', text)

        # === 策略A: 精确模板名或诊断名匹配（最高优先级）===
        exact_matches = []
        for tpl in self.templates:
            nm = tpl.get('name', '')
            dg = re.sub(r'\s+', '', tpl.get('diagnosis', ''))
            # 模板名或诊断名是输入的子串
            if nm and nm in t:
                exact_matches.append({
                    'template_id': tpl['id'], 'template_name': nm,
                    'score': 0.95, 'site': tpl['site'],
                    'discgroup': tpl.get('discgroup',''),
                    'description': tpl.get('description',''),
                    'diagnosis': tpl.get('diagnosis',''),
                })
            elif dg and len(dg) >= 4 and dg in t:
                exact_matches.append({
                    'template_id': tpl['id'], 'template_name': nm,
                    'score': 0.90, 'site': tpl['site'],
                    'discgroup': tpl.get('discgroup',''),
                    'description': tpl.get('description',''),
                    'diagnosis': dg,
                })
        if exact_matches:
            exact_matches.sort(key=lambda x: -x['score'])
            return exact_matches[:n]

        # === 策略B: knowledge 规则库匹配 ===
        try:
            knowledge_results = knowledge.match_with_rules(text, '')
            if knowledge_results:
                return knowledge_results[:n]
        except:
            pass

        # === 策略C: 原规则库关键词匹配 ===
        ts = self.sites(t)
        tk = set(re.findall(r'[一-鿿]{2,}', t))
        res = []

        for tpl in self.templates:
            d = re.sub(r'\s+', '', tpl.get('description', ''))
            dk = set(re.findall(r'[一-鿿]{2,}', d))
            ss = 0.0
            tss = set(tpl.get('sites', []))
            if ts and tss:
                inter = ts & tss
                if inter: ss = len(inter) / max(len(ts|tss), 1)
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
                    ns = len(ni) / max(len(nk), 1) * 0.6

            # 诊断关键词提升：模板诊断名完全匹配→直接高分
            dg = tpl.get('diagnosis', '')
            dg_clean = re.sub(r'\s+', '', dg) if dg else ''
            ds = 1.0 if dg_clean and dg_clean in t else 0.0

            # 短模板名直接命中提升
            name_in_text = nm and nm in t

            w = self.rb['match_strategy']['weights_no_hint']
            c = ds*w['diagnosis'] + ts2*w['text'] + ss*w['site'] + ns*w['name']

            # 模板名完全命中 → 大幅度提升
            if name_in_text:
                c = max(c, 0.70)

            # 短文本(<30字)：提高模板名权重
            if len(t) < 30:
                c = c * 0.6 + ns * 0.4

            if c >= 0.15:
                res.append({
                    'template_id': tpl['id'], 'template_name': tpl['name'],
                    'score': round(c,4), 'site': tpl['site'],
                    'discgroup': tpl.get('discgroup',''),
                    'description': tpl.get('description',''),
                    'diagnosis': tpl.get('diagnosis',''),
                })

        # === 策略D: 短文本模板名fallback ===
        if (not res or res[0]['score'] < 0.25) and len(t) < 40:
            name_matches = []
            for tpl in self.templates:
                nm = tpl.get('name', '')
                if nm:
                    nk = set(re.findall(r'[一-鿿]{2,}', nm))
                    if nk and tk:
                        inter = nk & tk
                        chinese_inter = sum(1 for c in nm if c in t)
                        score = chinese_inter / max(len(nm), 1)
                        if score >= 0.5:
                            name_matches.append({
                                'template_id': tpl['id'], 'template_name': nm,
                                'score': score * 0.7, 'site': tpl['site'],
                                'discgroup': tpl.get('discgroup',''),
                                'description': tpl.get('description',''),
                                'diagnosis': tpl.get('diagnosis',''),
                            })
            if name_matches:
                name_matches.sort(key=lambda x: -x['score'])
                # 与原结果合并
                res.extend(name_matches)

        # === 策略E: 路由规则补充 ===
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
                                'score': rr['score'],
                                'site': rr['site'],
                                'discgroup': tpl.get('discgroup',''),
                                'description': tpl.get('description',''),
                                'diagnosis': tpl.get('diagnosis',''),
                            })
                        break

        # 去重排序
        res.sort(key=lambda x: -x['score'])
        seen = set()
        unique = []
        for r in res:
            if r['template_id'] not in seen:
                seen.add(r['template_id'])
                unique.append(r)
        return unique[:n]

    def extract_variables(self, text):
        result = {}
        vr = self.rb.get('variable_rules', {})
        for var_name, rule in vr.items():
            matches = re.findall(rule['pattern'], text, re.IGNORECASE)
            if matches:
                result[var_name] = [list(m) if isinstance(m, tuple) else m for m in matches]
        return result

    def correct_asr(self, text: str) -> str:
        """使用knowledge混淆字典+语言模型修正ASR结果"""
        return knowledge.correct_asr_text(text)
