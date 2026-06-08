"""
超声语音报告系统 - ASR服务 v3 (无GPU优化版)
核心改进:
1. 结构化的initial_prompt构建（按部位分类注入热词）
2. 中文犹豫词/废话过滤（嗯啊呃那个这个）
3. 拼音混淆补充（声母韵母相似导致的识别错误）
4. 质量置信度评分（低分结果触发匹配增强）
"""
import os, tempfile, time, json, re
from pathlib import Path
from collections import Counter

HOTWORD_PATH = Path(__file__).parent / "medical_hotwords.json"

# ===== 中文犹豫词/废话过滤 =====
FILLER_WORDS = [
    "嗯", "呃", "啊", "哦", "嘛", "呗", "啦", "哟",
    "那个", "这个", "那个那个", "这个这个",
    "然后", "就是", "反正", "就是说", "这样的话",
    "对吧", "是吧", "对不对", "是不是",
    "我们", "咱们", "就是说呢",
]

# ===== 拼音混淆对（声母/韵母相似导致的误识别）=====
PINYIN_CONFUSIONS = [
    # 声母相似
    ("z", "zh"), ("c", "ch"), ("s", "sh"),
    ("l", "n"), ("r", "l"), ("f", "h"),
    ("b", "p"), ("d", "t"), ("g", "k"),
    ("j", "q"), ("q", "x"), ("j", "x"),
    # 韵母相似
    ("an", "ang"), ("en", "eng"), ("in", "ing"),
    ("ian", "iang"), ("uan", "uang"),
    ("ui", "ei"), ("iu", "ou"), ("ie", "ue"),
    ("ai", "ei"), ("ao", "ou"), ("ia", "ie"),
]

# ===== 超声场景高频词组（用于initial_prompt结构化注入）=====
SITE_PROMPTS = {
    "腹部": [
        "肝脏大小正常形态规则表面光滑实质回声分布均匀",
        "肝内管系尚清门静脉内径正常",
        "胆囊大小正常壁光滑透声可囊内未见明显异常回声",
        "胆总管内径正常",
        "脾厚正常实质回声分布均匀",
        "胰头厚正常胰体厚正常实质回声分布均匀",
        "双肾形态规则大小正常实质回声分布均匀",
    ],
    "心脏": [
        "各房室内径正常主肺动脉内径及位置关系正常",
        "各瓣膜清晰启闭自如",
        "室间隔及左室后壁不厚运动协调",
        "房室间隔未见明显连续中断",
        "心包及心包腔未见明显异常回声",
        "二尖瓣前叶曲线呈双峰前后叶运动异向",
        "CDFI房室间隔未见过隔血流",
    ],
    "甲状腺": [
        "甲状腺双侧叶形态规则大小正常",
        "表面光滑包膜完整实质回声分布均匀",
        "内未见明显结节及占位回声",
        "CDFI甲状腺内血流分布未见明显异常",
        "双侧颈部未见明显肿大淋巴结回声",
    ],
    "乳腺": [
        "双乳组织增厚增粗回声分布不均",
        "见多个粗大点片状低回声区呈豹纹征",
        "CDFI双乳内无异常血流信号",
        "双侧腋窝未见明显肿大淋巴结声像",
    ],
    "前列腺": [
        "前列腺大小约mm形态饱满",
        "实质回声欠均匀内未见明显包块回声",
        "膀胱充盈可内壁光滑",
    ],
    "子宫附件": [
        "子宫前位形态规则大小正常",
        "实质回声均匀宫腔线居中",
        "内膜厚约mm",
        "双侧附件区未见明显包块声像",
    ],
    "颈动脉": [
        "双侧颈动脉走形正常内膜光滑",
        "内中膜未增厚管腔内无明显斑块声像",
        "未见明显狭窄及扩张",
        "CDFI双侧颈总动脉颈内外动脉内血彩未见充盈缺损",
    ],
}

# ===== 医学单位标准化映射 =====
UNIT_NORMALIZE = {
    '豪米': 'mm', '毫米': 'mm', '公厘': 'mm',
    '离米': 'cm', '厘米': 'cm', '公分': 'cm',
    '好米': 'mm', '号米': 'mm',
}


class ASREngine:
    _instance = None
    _model = None
    _hotwords = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_hotwords(self) -> list:
        if self._hotwords is None:
            if HOTWORD_PATH.exists():
                try:
                    with open(HOTWORD_PATH, 'r', encoding='utf-8') as f:
                        self._hotwords = json.load(f).get('hotwords', [])
                except:
                    self._hotwords = self._build_hotwords()
            else:
                self._hotwords = self._build_hotwords()
        return self._hotwords

    def _build_hotwords(self) -> list:
        rb_path = Path(__file__).resolve().parent / "knowledge" / "超声规则库_rulebase.json"
        if not rb_path.exists():
            return ["肝脏","胆囊","胰腺","脾脏","肾脏","甲状腺","乳腺"]
        import json as _json
        with open(rb_path, 'r', encoding='utf-8') as f:
            rb = _json.load(f)
        terms = Counter()
        for t in rb.get('templates', []):
            text = (t.get('name','') + ' ' + t.get('description','') + ' ' + t.get('diagnosis',''))
            text = re.sub(r'\[[^\]]*\]', '', text)
            for m in re.findall(r'[一-鿿]{2,6}', text):
                terms[m] += 1
        stopwords = {'可以','没有','什么','如果','但是','因为','所以','而且','或者',
                     '虽然','然后','比较','已经','可能','需要','应该','这个','那个',
                     '这些','那些','这样','那样','这里','那里','一种','主要','以及',
                     '就是','之后','之间','分为','排除','左右','内径','可见','范围'}
        medical = [t for t, c in terms.most_common(800) if c >= 2 and len(t) >= 2 and t not in stopwords]
        medical.sort(key=lambda x: -len(x))
        hw_save = {"hotwords": medical[:500], "total": len(medical[:500]),
                   "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(HOTWORD_PATH, 'w', encoding='utf-8') as f:
            _json.dump(hw_save, f, ensure_ascii=False, indent=2)
        return medical[:500]

    def build_structured_prompt(self, text_hint: str = "") -> str:
        """
        构建结构化的initial_prompt
        如果检测到部位关键词，注入对应部位的高频描述
        否则注入通用超声描述
        """
        prompts = []
        # 检测部位
        site = "腹部"  # 默认
        if text_hint:
            for s in ['心脏','甲状腺','乳腺','前列腺','子宫附件','颈动脉','腹部']:
                if s in text_hint:
                    site = s
                    break

        # 注入部位特定的描述
        site_phrases = SITE_PROMPTS.get(site, SITE_PROMPTS['腹部'])
        prompts.extend(site_phrases)

        # 注入通用热词
        hotwords = self.get_hotwords()
        prompts.extend(hotwords[:30])

        return "。".join(prompts)

    def load_model(self, model_name='tiny'):
        if self._model is None:
            import whisper
            start = time.time()
            print(f'加载Whisper模型: {model_name}...')
            self._model = whisper.load_model(model_name)
            print(f'Whisper加载完成: {time.time()-start:.1f}s')
        return self._model

    def transcribe(self, audio_bytes: bytes, language='zh', text_hint: str = "") -> dict:
        model = self.load_model()

        # 构建结构化的initial_prompt
        prompt = self.build_structured_prompt(text_hint)

        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        try:
            tmp.write(audio_bytes)
            tmp.close()
            start = time.time()

            result = model.transcribe(
                tmp.name,
                language=language,
                task='transcribe',
                fp16=False,
                initial_prompt=prompt,
                temperature=0.0,
                best_of=1,
                beam_size=5,
                patience=1.5,
                condition_on_previous_text=True,
                compression_ratio_threshold=2.0,
                logprob_threshold=-1.0,
                no_speech_threshold=0.6,
            )

            elapsed = time.time() - start
            text = result['text'].strip()
            text = self._post_process(text)

            # 质量评分
            quality = self._score_quality(text)

            return {
                'text': text,
                'segments': result.get('segments', []),
                'language': result.get('language', 'zh'),
                'duration': elapsed,
                'hotwords_used': len(self.get_hotwords()),
                'quality_score': quality['score'],
                'quality_detail': quality['detail'],
            }
        finally:
            try: os.unlink(tmp.name)
            except: pass

    def _post_process(self, text: str) -> str:
        """增强版后处理"""
        if not text: return text

        # 1. 去空白
        text = re.sub(r'\s+', '', text)

        # 2. 去犹豫词/废话
        for fw in sorted(FILLER_WORDS, key=len, reverse=True):
            text = text.replace(fw, "")

        # 3. 去重复标点
        text = re.sub(r'[，,]{2,}', '，', text)
        text = re.sub(r'[。.]{2,}', '。', text)

        # 4. 单位标准化
        for wrong, correct in UNIT_NORMALIZE.items():
            if wrong in text:
                text = text.replace(wrong, correct)

        # 5. 数值格式修正
        text = re.sub(r'(\d)\s*[xX\*乘×]\s*(\d)', r'\1×\2', text)
        text = re.sub(r'(\d+)点(\d+)', r'\1.\2', text)

        # 6. 医学符号修正
        text = text.replace('x', '×')
        text = re.sub(r'(?<!\d)EF(\d+)', r'EF：\1%', text)
        text = re.sub(r'(?<!\d)FS(\d+)', r'FS：\1%', text)
        text = re.sub(r'(\d+)％', r'\1%', text)

        # 7. 问句清洗（医生可能口语化提问，需清理）
        text = re.sub(r'.*?[吗嘛呢]', '', text)
        text = re.sub(r'你看|你看一下|你看看|你帮我|帮我', '', text)
        text = re.sub(r'好了|行了吧|可以了吧|好嘞|好的', '', text)

        return text.strip()

    def _score_quality(self, text: str) -> dict:
        """
        ASR输出质量评分 (0-1)
        用于判断是否需要额外的知识库修正或匹配增强
        """
        if not text:
            return {'score': 0.0, 'detail': '空文本'}

        score = 1.0
        issues = []

        # 过短
        if len(text) < 5:
            score -= 0.3
            issues.append('过短')
        elif len(text) < 10:
            score -= 0.1
            issues.append('偏短')

        # 检查是否有中文
        cn_chars = len(re.findall(r'[一-鿿]', text))
        if cn_chars == 0:
            score -= 0.5
            issues.append('无中文字符')
        elif cn_chars < 5:
            score -= 0.2
            issues.append('中文字符过少')

        # 检查是否含有数字/单位但无中文
        if cn_chars == 0 and re.search(r'[\d.]+', text):
            score -= 0.3
            issues.append('纯数值文本')

        # 检查是否有超声关键词
        us_kw = ['肝','胆','脾','肾','心','甲状腺','乳腺','子宫','回声','mm','cm']
        kw_hits = sum(1 for kw in us_kw if kw in text)
        if kw_hits == 0:
            score -= 0.2
            issues.append('无超声关键词')

        # 检查是否有重复字符
        repeats = re.findall(r'(.)\1{3,}', text)
        if repeats:
            score -= 0.3
            issues.append(f'字符重复: {repeats[:3]}')

        return {
            'score': round(max(0.0, min(1.0, score)), 2),
            'detail': ';'.join(issues) if issues else '正常',
        }

    def transcribe_file(self, filepath: str, language='zh') -> dict:
        with open(filepath, 'rb') as f:
            return self.transcribe(f.read(), language=language)


asr = ASREngine()

if not HOTWORD_PATH.exists() or True:
    print("构建热词...")
    c = len(asr.get_hotwords())
    print(f"热词: {c}")
