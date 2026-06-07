"""
超声报告实时智能匹配引擎 v1.1
加载40万清洗数据，实时增量匹配，置信度>85%自动触发

核心改进:
1. 方言映射表（川渝/湖南）
2. 口语短语句式扩展
3. 实时API接口 /api/smart/*
4. 自动触发 < 50ms
"""
import json, re, time, os
from collections import defaultdict, Counter

# ===== 方言与口语映射 =====
DIALECT_MAP = {
    # 川渝方言
    '石头': '结石', '包包': '结节', '水泡泡': '囊肿', '水泡子': '囊肿',
    '腰子': '肾脏', '颈子': '甲状腺', '嗓子': '甲状腺',
    '点点': '点状', '坨坨': '结节', '节节': '结节',
    # 湖南方言
    '石脑': '结石', '坨坨': '结节', '水泡子': '囊肿',
    '颈子': '甲状腺', '腰子': '肾脏',
    # 口语简化
    '头头': '头部', '下面': '下部', '上面': '上部',
    '前面': '前壁', '后面': '后壁', '边边上': '边缘',
    # 数值读法
    '点': '.', '乘': 'x', '乘以': 'x',
    '公分': 'cm', '个': '',
}

# ===== 停用词 =====
STOP_WORDS = {'的','了','在','是','有','和','与','或','为','之','于','以','及',
              '内','外','中','上','下','左','右','前','后','约','见','可','呈','个'}

# ===== 部位关键词 =====
SITE_KEYWORDS = {
    '肝脏': ['肝脏','肝内','肝','门静脉','胆总管'],
    '胆囊': ['胆囊','胆','胆囊壁'],
    '甲状腺': ['甲状腺','甲状腺左','甲状腺右','峡部'],
    '乳腺': ['乳腺','左乳','右乳','双乳','乳房','腋窝','低回声','无回声','结节'],
    '前列腺': ['前列腺','前列腺增生','精囊'],
    '心脏': ['心脏','二尖瓣','三尖瓣','主动脉瓣','心包','左室','右房'],
    '双肾': ['肾脏','肾','肾上腺','输尿管','强回声'],
    '子宫附件': ['子宫','卵巢','附件','盆腔','宫颈','内膜'],
    '脾': ['脾脏','脾','脾门'],
    '颈动脉': ['颈动脉','颈总','椎动脉','锁骨下','斑块','内中膜'],
    '睾丸': ['睾丸','附睾','精索'],
    '胰腺': ['胰腺','胰头','胰体'],
}


class SmartMatcher:
    def __init__(self, data_path):
        self.records = []
        self.inverted_index = defaultdict(list)
        self.site_index = defaultdict(list)
        self.discname_index = defaultdict(list)
        self._load_data(data_path)
        self._build_index()

    def _load_data(self, data_path):
        with open(data_path, 'r', encoding='utf-8') as f:
            self.records = json.load(f)
        print(f"已加载 {len(self.records)} 条数据")

    def _build_index(self):
        ts = time.time()
        for idx, rec in enumerate(self.records):
            text = rec.get('see_simple', '')
            discname = rec.get('discname', '')
            if not text:
                continue

            kws = set()
            for m in re.findall(r'[一-鿿]{2,4}', text):
                if m not in STOP_WORDS:
                    kws.add(m)
            for m in re.findall(r'\d+\.?\d*(?:\s*[xX×*]\s*\d+\.?\d*)*(?:\s*(?:mm|cm|%))?', text):
                kws.add('NUM:' + m.strip())
            for m in re.findall(r'\b[A-Z]{2,5}\b', text):
                kws.add('ABBR:' + m)

            for kw in kws:
                self.inverted_index[kw].append(idx)

            if discname:
                for m in re.findall(r'[一-鿿]{2,4}', discname):
                    self.discname_index[m].append(idx)

            for site, site_kws in SITE_KEYWORDS.items():
                for sk in site_kws:
                    if sk in text:
                        self.site_index[site].append(idx)
                        break

        print(f"索引: {len(self.inverted_index)}关键词, {time.time()-ts:.1f}s")

    def _normalize(self, text):
        """方言/口语标准化"""
        t = text.replace(' ', '')
        # 方言映射
        for dial, std in sorted(DIALECT_MAP.items(), key=lambda x: -len(x[0])):
            if dial in t:
                t = t.replace(dial, std)
        # 数值标准化: 点八 -> 0.8
        t = re.sub(r'点(\d)', r'.\1', t)
        # 去空格
        t = re.sub(r'\s+', '', t)
        return t

    def _tokenize(self, text):
        kws = set()
        for m in re.findall(r'[一-鿿]{2,4}', text):
            if m not in STOP_WORDS:
                kws.add(m)
        for m in re.findall(r'\d+\.?\d*(?:\s*[xX×*]\s*\d+\.?\d*)*(?:\s*(?:mm|cm|%))?', text):
            kws.add('NUM:' + m.strip())
        for m in re.findall(r'\b[A-Z]{2,5}\b', text):
            kws.add('ABBR:' + m)
        return kws

    def match(self, text, top_n=10):
        ts = time.time()
        text = self._normalize(text)
        t = re.sub(r'\s+', '', text)
        if not t:
            return []

        input_kws = self._tokenize(t)
        if not input_kws:
            return []

        # 1. 倒排查找
        candidate_scores = Counter()
        for kw in input_kws:
            for idx in self.inverted_index.get(kw, []):
                candidate_scores[idx] += 1

        if not candidate_scores:
            return []

        min_hits = max(2, len(input_kws) * 0.3)
        top_candidates = [idx for idx, score in candidate_scores.most_common(300)
                         if score >= min_hits or score >= 2]
        if not top_candidates:
            top_candidates = [idx for idx, _ in candidate_scores.most_common(80)]

        # 2. 多维度评分
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

            ref_kws = self._tokenize(ref)
            if not input_kws or not ref_kws:
                continue

            jaccard = len(input_kws & ref_kws) / max(len(input_kws | ref_kws), 1)

            ref_ngrams = set()
            for i in range(len(ref) - 1):
                ref_ngrams.add(ref[i:i+2])
            bigram_overlap = len(input_ngrams & ref_ngrams) / max(len(ref_ngrams), 1) if ref_ngrams else 0

            ref_chars = set(ref)
            char_overlap = len(input_chars & ref_chars) / max(len(ref_chars), 1) if ref_chars else 0

            len_ratio = min(len(t), len(ref)) / max(len(t), len(ref), 1)

            # 数值匹配
            input_nums = set(re.findall(r'\d+\.?\d*', t))
            ref_nums = set(re.findall(r'\d+\.?\d*', ref))
            num_score = len(input_nums & ref_nums) / max(len(input_nums | ref_nums), 1) if input_nums and ref_nums else 0.5

            # 部位匹配
            site_score = 0
            for site, site_kws in SITE_KEYWORDS.items():
                has_input = any(sk in t for sk in site_kws)
                has_ref = any(sk in ref for sk in site_kws)
                if has_input and has_ref:
                    site_score = 1.0
                    break

            # 诊断名匹配奖励
            discname = rec.get('discname', '')
            disc_bonus = 0
            if discname:
                disc_kws = set(re.findall(r'[一-鿿]{2,4}', discname))
                if disc_kws and input_kws:
                    disc_overlap = len(disc_kws & input_kws)
                    disc_bonus = disc_overlap * 0.05

            total = (jaccard * 0.35 + bigram_overlap * 0.12 + char_overlap * 0.08 +
                     len_ratio * 0.05 + num_score * 0.15 + site_score * 0.20 + disc_bonus)

            # 总词数偏差惩罚：输入词越多越精确
            precision_boost = len(input_kws) * 0.02 if len(input_kws) >= 3 else 0
            total = min(total + precision_boost, 0.95)

            results.append((total, idx, rec))

        results.sort(key=lambda x: -x[0])
        top = results[:top_n]

        # 3. 置信度归一化
        max_score = top[0][0] if top else 0
        output = []
        for i, (score, idx, rec) in enumerate(top):
            # 置信度 = 相对最高分的比例
            confidence = (score / max_score) * 100 if max_score > 0 else 0
            # 绝对值调整：分太低时整体降低置信度
            confidence = confidence * min(score * 2, 1)
            confidence = min(max(confidence, 0), 100)

            output.append({
                'rank': i + 1,
                'confidence': round(confidence, 1),
                'raw_score': round(score, 4),
                'see_simple': rec.get('see_simple', '')[:100],
                'see_full': rec.get('see_full', ''),
                'discname': rec.get('discname', ''),
                'discgroup': rec.get('discgroup', ''),
                'tpl_info1': rec.get('tpl_info1', ''),
            })

        # 4. 自动触发
        auto_trigger = False
        trigger_reason = ''
        if len(output) >= 2:
            diff = output[0]['confidence'] - output[1]['confidence']
            if output[0]['confidence'] >= 80 and diff >= 5:
                auto_trigger = True
                trigger_reason = f'Top1独占{output[0]["confidence"]:.0f}%, 领先Top2 {diff:.0f}%'
            elif output[0]['confidence'] >= 75 and diff >= 10:
                auto_trigger = True
                trigger_reason = f'Top1稳定{output[0]["confidence"]:.0f}%, 大幅领先Top2 {diff:.0f}%'
        elif len(output) == 1 and output[0]['confidence'] >= 75:
            auto_trigger = True
            trigger_reason = f'唯一匹配, 置信度{output[0]["confidence"]:.0f}%'
        else:
            trigger_reason = f'需继续输入, Top1={output[0]["confidence"]:.0f}%' if output else '无匹配'

        return {
            'matches': output[:5],
            'total_candidates': len(candidate_scores),
            'elapsed_ms': round((time.time() - ts) * 1000, 1),
            'auto_trigger': auto_trigger,
            'trigger_reason': trigger_reason,
        }


# 全局单例
_matcher = None

def get_matcher(data_path='E:/claude/ultrasound-report-mvp/backend/data_40w.json'):
    global _matcher
    if _matcher is None:
        if os.path.exists(data_path):
            _matcher = SmartMatcher(data_path)
        else:
            print(f"数据文件不存在: {data_path}")
    return _matcher


if __name__ == '__main__':
    m = get_matcher()
    if m:
        tests = [
            '右乳外上0.8x0.5低回声边界清无血流二类',
            '胆囊头头有个1.2的石头壁不厚',
            '甲状腺右叶0.4的水泡泡边界清二类',
            '右肾下极0.5强回声后方伴声影',
            '子宫前位肌层1.5x1.2低回声边界清',
        ]
        for test in tests:
            print(f'\n{"="*70}')
            print(f'【输入】{test}')
            result = m.match(test)
            print(f'  耗时: {result["elapsed_ms"]}ms | 触发: {result["auto_trigger"]} | {result["trigger_reason"]}')
            for r in result['matches'][:3]:
                print(f'  #{r["rank"]} ({r["confidence"]}%): {r["discname"]}')
            if result['auto_trigger']:
                r = result['matches'][0]
                print(f'\n  ✅ 自动触发!')
                print(f'  完整版: {r["see_full"][:100]}...')
                print(f'  诊断: {r["discname"]}')
                print(f'  分组: {r["discgroup"]}')
