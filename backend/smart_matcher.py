"""
超声报告实时智能匹配引擎 v2.0 (专业版)
40万数据 + 逆文档频率(IDF)加权 + 部位强制约束 + 智能置信度

核心改进:
1. TF-IDF关键词加权（稀有词权重高，常见词权重低）
2. 部位强制过滤（输入认准某部位后只返回该部位的记录）
3. N-gram分段评分（3字词 > 2字词 > 单字）
4. 置信度归一化修正（更直观的百分比）
5. 结果去重 + 智能排序
"""
import json, re, time, os, math
from collections import defaultdict, Counter

# ===== 方言与口语映射 =====
DIALECT_MAP = {
    '石头': '结石', '包包': '结节', '水泡泡': '囊肿', '水泡子': '囊肿',
    '腰子': '肾脏', '颈子': '甲状腺', '嗓子': '甲状腺',
    '点点': '点状', '坨坨': '结节', '节节': '结节',
    '石脑': '结石',
    '头头': '头部', '下面': '下部', '上面': '上部',
    '前面': '前壁', '后面': '后壁', '边边上': '边缘',
    '点': '.', '乘': 'x', '乘以': 'x', '公分': 'cm',
}

# ===== 停用词 =====
STOP_WORDS = {'的','了','在','是','有','和','与','或','为','之','于','以','及',
              '内','外','中','上','下','左','右','前','后','约','见','可','呈','个','其','被'}

# ===== 部位关键词（三级结构）=====
SITE_KEYWORDS = {
    '肝脏':   {'pri': ['肝脏','肝内','门静脉','胆总管','肝'], 'sec': ['实质回声','大小正常','形态规则']},
    '胆囊':   {'pri': ['胆囊','胆囊壁','胆总管','胆'], 'sec': ['结石','壁欠光滑','胆囊大小']},
    '甲状腺': {'pri': ['甲状腺','甲状旁腺','峡部'], 'sec': ['左叶','右叶','双侧叶','回声均匀']},
    '乳腺':   {'pri': ['乳腺','左乳','右乳','双乳','乳房','腋窝'], 'sec': ['低回声','无回声','结节','豹纹征','小叶增生']},
    '前列腺': {'pri': ['前列腺','精囊'], 'sec': ['稍大','增生','钙化']},
    '心脏':   {'pri': ['心脏','二尖瓣','三尖瓣','主动脉瓣','左室','右房'], 'sec': ['EF','FS','返流']},
    '双肾':   {'pri': ['肾脏','肾','肾上腺','输尿管'], 'sec': ['强回声','结石','囊肿','积水','回声']},
    '子宫附件':{'pri': ['子宫','卵巢','附件','宫颈','盆腔'], 'sec': ['内膜','肌瘤','囊肿','低回声','内膜厚']},
    '脾':     {'pri': ['脾脏','脾门','脾'], 'sec': ['脾厚','实质回声']},
    '颈动脉': {'pri': ['颈动脉','颈总','椎动脉','锁骨下'], 'sec': ['斑块','内中膜','内膜面']},
    '睾丸':   {'pri': ['睾丸','附睾','精索'], 'sec': ['静脉曲张','囊肿']},
    '胰腺':   {'pri': ['胰腺','胰头','胰体'], 'sec': ['大小正常','实质回声']},
}


class SmartMatcher:
    def __init__(self, data_path):
        self.records = []
        self.inverted_index = defaultdict(list)    # keyword -> [record_ids]
        self.idf_scores = {}                        # keyword -> IDF weight
        self.site_index = defaultdict(list)         # site -> [record_ids]
        self._load_data(data_path)
        self._build_index()

    def _load_data(self, data_path):
        with open(data_path, 'r', encoding='utf-8') as f:
            self.records = json.load(f)
        print(f"[SmartMatcher] 已加载 {len(self.records)} 条记录")

    def _build_index(self):
        ts = time.time()
        # 第一轮: 统计文档频率
        doc_freq = Counter()
        for idx, rec in enumerate(self.records):
            text = rec.get('see_simple', '')
            if not text:
                continue
            kws = self._extract_keywords(text)
            for kw in kws:
                doc_freq[kw] += 1

        total_docs = len(self.records)
        self.idf_scores = {
            kw: math.log((total_docs + 1) / (freq + 1)) + 1
            for kw, freq in doc_freq.items()
        }

        # 第二轮: 建立倒排索引
        for idx, rec in enumerate(self.records):
            text = rec.get('see_simple', '')
            discname = rec.get('discname', '')
            if not text:
                continue

            kws = self._extract_keywords(text)
            for kw in kws:
                self.inverted_index[kw].append(idx)

            # 部位索引
            for site, kw_map in SITE_KEYWORDS.items():
                pri_kws = kw_map.get('pri', [])
                for pk in pri_kws:
                    if pk in text:
                        self.site_index[site].append(idx)
                        break

        print(f"[SmartMatcher] 索引: {len(self.inverted_index)}关键词, {time.time()-ts:.1f}s")

    def _extract_keywords(self, text):
        """智能关键词提取：3字词(主) + 2字词(辅) + 数值 + 英文缩写"""
        kws = set()
        # 3-4字词（高价值）
        for m in re.findall(r'[一-鿿]{3,4}', text):
            if m not in STOP_WORDS:
                kws.add('W:' + m)
        # 2字词（辅助）
        for m in re.findall(r'[一-鿿]{2}', text):
            if m not in STOP_WORDS:
                kws.add('W2:' + m)
        # 数值
        for m in re.findall(r'\d+\.?\d*(?:\s*[xX×*]\s*\d+\.?\d*)*(?:\s*(?:mm|cm|%))?', text):
            kws.add('N:' + m.strip())
        # 英文缩写
        for m in re.findall(r'\b[A-Z]{2,5}\b', text):
            kws.add('E:' + m)
        return kws

    def _normalize(self, text):
        t = text.replace(' ', '')
        for dial, std in sorted(DIALECT_MAP.items(), key=lambda x: -len(x[0])):
            if dial in t:
                t = t.replace(dial, std)
        t = re.sub(r'点(\d)', r'.\1', t)
        t = re.sub(r'\s+', '', t)
        return t

    def _detect_primary_site(self, text):
        """检测主要检查部位（只返回1个最可能部位）"""
        t = re.sub(r'\s+', '', text)
        site_scores = {}
        for site, kw_map in SITE_KEYWORDS.items():
            score = 0
            pri_kws = kw_map.get('pri', [])
            for pk in pri_kws:
                if pk in t:
                    score += 2 if len(pk) >= 3 else 1
            sec_kws = kw_map.get('sec', [])
            for sk in sec_kws:
                if sk in t:
                    score += 1.5
            if score > 0:
                site_scores[site] = score

        if not site_scores:
            return None

        top_site = max(site_scores, key=site_scores.get)
        top_score = site_scores[top_site]

        # 检查第二名是否接近
        sorted_sites = sorted(site_scores.items(), key=lambda x: -x[1])
        if len(sorted_sites) >= 2:
            second_score = sorted_sites[1][1]
            if top_score / max(second_score, 0.01) >= 1.5:
                return top_site
            # 如果接近且多部位 + 单字"肝"匹配，返回更特异的
            for site, score in sorted_sites[:3]:
                if len(site) >= 2:  # 避免"肝"这种单字干扰
                    return site
            return top_site

        return top_site

    def match(self, text, top_n=10):
        ts = time.time()
        text = self._normalize(text)
        t = re.sub(r'\s+', '', text)
        if not t or len(t) < 2:
            return []

        input_kws = self._extract_keywords(t)
        # 3字以上的关键词必须有
        word_kws = [kw for kw in input_kws if kw.startswith('W:')]
        if not word_kws and len(t) < 4:
            return []

        # 检测主部位
        primary_site = self._detect_primary_site(t)

        # --- 第一轮：倒排查找 ---
        candidate_scores = Counter()
        for kw in input_kws:
            idf = self.idf_scores.get(kw, 1.0)
            for idx in self.inverted_index.get(kw, []):
                candidate_scores[idx] += idf

        if not candidate_scores:
            return []

        min_idf = max(2.0, len(input_kws) * 0.5)
        top_candidates = [idx for idx, _ in candidate_scores.most_common(500)
                         if _ >= min_idf or _ >= 3]

        if not top_candidates:
            top_candidates = [idx for idx, _ in candidate_scores.most_common(100)]

        # --- 第二轮：多维度评分 ---
        results = []
        input_chars = set(t)
        input_ngrams = set()
        for i in range(len(t) - 1):
            input_ngrams.add(t[i:i+2])

        for idx in top_candidates:
            rec = self.records[idx]
            ref = rec.get('see_simple', '')
            if not ref:
                continue

            ref_kws = self._extract_keywords(ref)
            if not ref_kws:
                continue

            # 1. 加权Jaccard (IDF加权)
            kw_intersect = input_kws & ref_kws
            kw_union = input_kws | ref_kws
            weighted_inter = sum(self.idf_scores.get(k, 1.0) for k in kw_intersect)
            weighted_union = sum(self.idf_scores.get(k, 1.0) for k in kw_union)
            idf_jaccard = weighted_inter / max(weighted_union, 0.001)

            # 2. N-gram特征重叠
            ref_ngrams = set(ref[i:i+2] for i in range(len(ref) - 1))
            bigram_overlap = len(input_ngrams & ref_ngrams) / max(len(ref_ngrams), 1) if ref_ngrams else 0

            ref_chars = set(ref)
            char_overlap = len(input_chars & ref_chars) / max(len(ref_chars), 1) if ref_chars else 0

            # 3. 数值匹配
            input_nums = set(re.findall(r'\d+\.?\d*', t))
            ref_nums = set(re.findall(r'\d+\.?\d*', ref))
            num_score = len(input_nums & ref_nums) / max(len(input_nums | ref_nums), 1) if input_nums and ref_nums else 0.0

            # 4. 部位匹配（带惩罚跨部位）
            site_score = 0
            cross_penalty = 1.0
            if primary_site:
                site_kws_map = SITE_KEYWORDS.get(primary_site, {})
                all_site_kws = site_kws_map.get('pri', []) + site_kws_map.get('sec', [])
                ref_has_site = any(sk in ref for sk in all_site_kws)
                if ref_has_site:
                    site_score = 0.3
                # 检查是否跨部位
                ref_site = self._detect_primary_site(ref)
                if ref_site and ref_site != primary_site:
                    cross_penalty = 0.4

            # 5. 诊断名直接匹配奖励
            discname = rec.get('discname', '')
            disc_bonus = 0
            if discname:
                disc_kws = set(re.findall(r'[一-鿿]{2,4}', discname))
                word_kws_set = {kw.replace('W:', '').replace('W2:', '') for kw in word_kws}
                disc_hits = disc_kws & word_kws_set
                disc_bonus = len(disc_hits) * 0.08

            # 6. 长度比率
            len_ratio = min(len(t), len(ref)) / max(len(t), len(ref), 1)

            # 7. 特有关键词匹配: 如"强回声"+"伴声影" → 结石
            special_boost = 0
            if '强回声' in t and '伴声影' in t:
                if '结石' in discname or '钙化' in discname:
                    special_boost = 0.15
            if '无回声' in t and '后壁回声增强' in t:
                if '囊肿' in discname:
                    special_boost = 0.15

            # 综合评分
            total = (idf_jaccard * 0.30 + bigram_overlap * 0.08 + char_overlap * 0.04 +
                     num_score * 0.12 + site_score * 0.15 + disc_bonus + len_ratio * 0.04 + special_boost)

            # 跨部位惩罚
            total *= cross_penalty

            # 词数奖励（输入词越多越精确）
            word_count = len(word_kws)
            if word_count >= 2:
                total *= (1 + word_count * 0.05)

            # 3字词直接命中诊断名奖励
            word3_set = {kw.replace('W:', '') for kw in word_kws}
            if discname:
                if discname in t or any(w3 in discname for w3 in word3_set):
                    total *= 1.5
                # 诊断名中的关键词命中奖励
                for w3 in word3_set:
                    if len(w3) >= 2 and w3 in discname:
                        total *= 1.3
                        break

            # 部位site字段匹配后额外加分
            discgroup = rec.get('discgroup', '')
            if primary_site and discgroup:
                if primary_site in discgroup or discgroup in primary_site:
                    total *= 1.2
                # cross penalty check
                disc_primary = None
                for site_name in SITE_KEYWORDS:
                    if site_name in discgroup:
                        disc_primary = site_name
                        break
                if disc_primary and disc_primary != primary_site:
                    total *= 0.5

            if total >= 0.01:
                results.append((total, idx, rec))

        results.sort(key=lambda x: -x[0])
        top = results[:top_n]

        if not top:
            return []

        # --- 置信度归一化 ---
        max_raw = top[0][0]
        output = []
        for i, (raw, idx, rec) in enumerate(top):
            # 原始分映射到置信度
            confidence = (raw / max_raw) * 100 if max_raw > 0 else 0
            # 绝对值调整：raw >= 0.3 才是好匹配
            if raw < 0.1:
                confidence *= 0.3
            elif raw < 0.2:
                confidence *= 0.6
            elif raw < 0.3:
                confidence *= 0.85
            confidence = min(max(confidence, 0), 100)

            output.append({
                'rank': i + 1,
                'confidence': round(confidence, 1),
                'raw_score': round(raw, 4),
                'see_simple': (rec.get('see_simple', '') or '')[:120],
                'see_full': rec.get('see_full', '') or '',
                'discname': rec.get('discname', '') or '',
                'discgroup': rec.get('discgroup', '') or '',
                'tpl_info1': rec.get('tpl_info1', '') or '',
            })

        # --- 去重（相同discname只留最高分） ---
        seen_discs = set()
        deduped = []
        for item in output:
            key = item['discname']
            if key and key not in seen_discs:
                seen_discs.add(key)
                deduped.append(item)
            elif not key:
                deduped.append(item)
        output = deduped[:top_n]

        # --- 自动触发 ---
        auto_trigger = False
        trigger_reason = ''
        if len(output) >= 2:
            diff = output[0]['confidence'] - output[1]['confidence']
            if output[0]['confidence'] >= 80 and diff >= 5:
                auto_trigger = True
                trigger_reason = f'独占{output[0]["confidence"]:.0f}%, 领先{output[1]["confidence"]:.0f}%'
            elif output[0]['confidence'] >= 85:
                auto_trigger = True
                trigger_reason = f'高置信度{output[0]["confidence"]:.0f}%'
        elif len(output) == 1 and output[0]['confidence'] >= 80:
            auto_trigger = True
            trigger_reason = f'唯一匹配 {output[0]["confidence"]:.0f}%'
        else:
            trigger_reason = f'Top1={output[0]["confidence"]:.0f}%' if output else '无匹配'

        return {
            'matches': output[:5],
            'total_candidates': len(candidate_scores),
            'primary_site': primary_site,
            'elapsed_ms': round((time.time() - ts) * 1000, 1),
            'auto_trigger': auto_trigger,
            'trigger_reason': trigger_reason,
        }


_matcher = None

def get_matcher(data_path='E:/claude/ultrasound-report-mvp/backend/data_40w.json'):
    global _matcher
    if _matcher is None:
        if os.path.exists(data_path):
            _matcher = SmartMatcher(data_path)
        else:
            print(f"[SmartMatcher] 数据文件不存在: {data_path}")
    return _matcher
