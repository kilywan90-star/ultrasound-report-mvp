"""
超声语音报告系统 - 知识引擎（基于 knowledge/loader 统一加载器）
"""
import re
from pathlib import Path
from knowledge.loader import get_kb


class KnowledgeEngine:
    """知识引擎 — 包装 KnowledgeBase, 提供业务接口"""

    def __init__(self):
        kb = get_kb()
        # 从统一加载器获取数据
        self.confusion_dict = kb.confusion_dict
        self.exam_catalog = kb.exam_part_routing or {}
        self.template_fields = kb.high_conf_candidates or {}
        self.section_templates = kb.matching_rules_merged or {}

        # ASR热词
        self.hotwords = []
        self.hotwords_auto = []
        try:
            import json
            hw_file = Path(__file__).resolve().parent / "knowledge" / "hotwords.json"
            if hw_file.exists():
                hw = json.loads(hw_file.read_text(encoding='utf-8'))
                self.hotwords = hw.get('terms', [])
            auto_file = Path(__file__).resolve().parent / "knowledge" / "asr_hotwords_auto.json"
            if auto_file.exists():
                auto = json.loads(auto_file.read_text(encoding='utf-8'))
                self.hotwords_auto = auto.get('hotwords', [])
        except Exception:
            pass

        # ASR语言模型
        self.language_model = kb.asr_language_model
        lm = self.language_model
        ngram = lm.get('ngram_language_model', {})
        self.ngram_patterns = ngram.get('high_freq_patterns', []) if isinstance(ngram, dict) else []
        cr = lm.get('contextual_correction_rules', {})
        self.correction_rules = cr.get('rules', []) if isinstance(cr, dict) else []

        # 方言映射
        dm = kb.confusion_dict or {}
        self.dialect_mapping = dm if isinstance(dm, dict) else {}

        self.master_rules = kb.confusion_dict
        self.organ_disease = kb.site_disease or {}

        print(f"知识引擎就绪: {len(self.hotwords)}热词 + {len(self.ngram_patterns)}高频模式 + {len(self.correction_rules)}修正规则")

    # ===== 对外接口 =====

    def correct_asr_text(self, text: str) -> str:
        """
        ASR后处理修正引擎 (v2.5) — 集成mvp项目的完整4层纠错
        L1: 混淆词典替换 (word→word, 长词优先)
        L2: 数值标准化 (单位/小数/数字格式)
        L3: 模式修正 (结构/标点/医学符号)
        L4: 幻觉清洗 (ASR流式重复/无意义串)
        """
        if not text:
            return text

        # ===== L1: 混淆词典替换 =====
        confusion_map = self._build_full_confusion_map()

        for wrong in sorted(confusion_map.keys(), key=len, reverse=True):
            if wrong in text and confusion_map[wrong] not in text:
                text = text.replace(wrong, confusion_map[wrong])

        # 额外单字修正
        char_fixes = {'干': '肝', '甘': '肝', '杆': '肝', '郎': '胆', '狼': '胆',
                      '线': '腺', '月': '约', '必': '壁', '毕': '壁', '币': '壁',
                      '课': '可', '科': '可', '建': '见', '件': '见', '好': '毫'}
        for w, c in char_fixes.items():
            if w in text and c not in text:
                text = text.replace(w, c)

        # ===== L2: 数值标准化 =====
        text = re.sub(r"(\d+)点(\d+)", r"\1.\2", text)
        text = re.sub(r"(\d+(?:\.\d+)?)\s*公分", r"\1cm", text)
        text = re.sub(r"(\d+(?:\.\d+)?)\s*[豪毫]米", r"\1mm", text)
        text = re.sub(r"(\d+(?:\.\d+)?)\s*[离厘]米", r"\1cm", text)
        text = re.sub(r"(\d)\s*[xX\*乘×]\s*(\d)", r"\1×\2", text)

        # ===== L3: 模式修正 =====
        text = re.sub(r"[Ss]\s*[/／]\s*[Dd]\s*[：:＝=]?\s*(\d)", r"S/D \1", text)
        text = re.sub(r"RI\s*[Ii1l]\s*[：:＝=]?\s*(\d)", r"RI \1", text)
        text = re.sub(r"PI\s*[：:＝=]?\s*(\d)", r"PI \1", text)
        text = re.sub(r"Vma[x×X]\s*[：:＝=]?\s*(\d)", r"Vmax \1", text)
        text = re.sub(r"(\d+)\s*[次ci]?\s*[/／]\s*分", r"\1次/分", text)
        text = re.sub(r"[一1]级", "I级", text)
        text = re.sub(r"[二2]级", "II级", text)
        text = re.sub(r"[三3]级", "III级", text)
        text = re.sub(r"([。，、，])\1+", r"\1", text)

        # ===== L4: 幻觉清洗 =====
        hallucination = ["建板郎", "见板郎", "见板囊", "建板囊",
                         "相三三", "香三三", "象三三",
                         "做做腹部彩超", "采做腹部彩超", "座座腹部彩超",
                         "做做腹部", "采做腹部", "座座腹部",
                         "所建建板", "所建见板", "压缩到", "压缩", "压到",
                         "做做", "左左", "采做"]
        for hw in hallucination:
            text = text.replace(hw, "")
        text = re.sub(r"腹部\s*彩\s*超", "腹部彩超", text)

        # 收尾
        text = re.sub(r"[ ]{2,}", " ", text)
        text = re.sub(r"([。，、；：])\s*", r"\1", text)
        return text.strip()

    def _build_full_confusion_map(self) -> dict:
        """构建完整混淆映射"""
        result = {}

        # 1. confusion_dict.json 中的
        for standard, candidates in self.confusion_dict.items():
            if isinstance(candidates, list):
                for cand in candidates:
                    if cand and cand not in result:
                        result[cand] = standard

        # 2. 短语映射
        phrase_map = {
            '回声': ['回生', '会声'], '均匀': ['军匀', '君匀', '郡匀', '俊匀'],
            '形态': ['行态', '型态', '形太', '刑态'],
            '规则': ['龟则', '归则', '鬼则', '硅则'],
            '正常': ['郑常', '正长', '镇常'],
            '实质': ['石质', '识质', '实时'],
            '子宫': ['子工'], '附件': ['附近'],
            '前列腺': ['钱列腺', '前裂线', '前列线', '千列腺'],
            '双侧': ['双策', '双测', '双册', '霜侧'],
            '未见': ['为见', '无见', '末见', '未建', '为建'],
            '大小': ['打小', '大少'],
            '囊肿': ['囊种', '郎肿', '狼肿', '囊重'],
            '毫米': ['好米', '豪米', '号米'],
            '表面': ['表满', '表明', '彪面'],
            '包膜': ['包摸', '保膜', '宝膜', '胞膜'],
            '光滑': ['光滑', '广滑', '光化', '光花', '光划'],
            '边界': ['边结'],
            '清晰': ['清析', '清希', '青晰', '轻晰'],
            '肿大': ['种大', '仲大', '钟大'],
            '淋巴结': ['林巴结', '淋疤节', '林八节', '琳巴结', '零八结', '淋吧结', '林巴'],
            '甲状腺': ['甲壮线', '甲壮腺', '甲状线', '甲庄线', '钾状腺', '甲装线', '谁说剑侠', '谁缩剑侠'],
            '壁薄': ['必薄', '毕薄', '币薄', '地薄'],
            '增厚': ['增后', '曾厚', '增侯', '增候', '争厚', '曾候'],
            '毛糙': ['毛操', '毛草', '毛曹', '毛超', '毛少', '矛糙', '毛皂'],
            '血流信号': ['血留信号', '写流信号', '血流信好'],
            '包膜完整': ['包模完整', '薄模完整', '包摸完整', '包模完正', '包膜完真'],
            '未见明显异常': ['未见名显异常', '未见明天异常'],
            '胆囊': ['胆郎', '胆狼', '胆朗', '单囊', '胆廊'],
            '肝脏': ['肝藏', '肝张', '肝章', '干脏', '甘藏'],
            '盆腔': ['盆墙', '盆强', '喷墙'],
            '绕颈': ['扰颈', '绕经', '绕紧', '扰经', '扰紧'],
            '双顶径': ['双顶经', '双定径', '伤顶径'],
            '股骨长': ['股骨常', '古骨长', '鼓骨长'],
            '肱骨长': ['红骨长', '工骨常', '公骨长'],
            '羊水': ['洋水', '杨水', '阳水', '洋随'],
            '胎盘': ['胎潘', '太盘', '台盘'],
            '脐带': ['期待', '奇带', '其带', '脐戴'],
            '无回声': ['无回生', '吴回声', '五回声'],
            '低回声': ['低回生', '底回声', '狄回声'],
            '高回声': ['高回生', '高会生'],
            '强回声': ['强回生', '墙回声', '强会生'],
            '混合回声': ['混合回生', '魂和会生'],
            '血流丰富': ['丰富血留', '风富血流'],
            '分离': ['分立', '芬离', '分理'],
            '弥漫': ['迷漫', '米漫', '迷慢'],
            '弥漫性': ['迷慢性', '米慢性', '迷满性'],
            '结节': ['接节', '结结', '捷节', '洁洁', '节节', '结杰', '节结'],
            '中孕': ['中运', '中韵', '中蕴'],
            '四维': ['4维', '4为', '四为', '思维', '四位'],
            '四维彩超': ['4维彩超', '思维彩超', '四为彩超'],
            '臀位': ['同位', '屯位', '豚位'],
            '头位': ['投喂', '头卫', '头未'],
            '周': ['WD', 'w', '周'],
            '周数': ['周书', '周术', '周数数'],
            'WD': ['w'],
        }
        for correct, wrongs in phrase_map.items():
            for w in wrongs:
                if w and w not in result:
                    result[w] = correct

        return result

    def get_hotwords_for_asr(self) -> list:
        """获取给Whisper的initial_prompt热词列表"""
        all_terms = []
        all_terms.extend(self.hotwords)
        for item in self.hotwords_auto:
            word = item.get('word', '') if isinstance(item, dict) else str(item)
            if word and len(word) >= 2:
                all_terms.append(word)

        seen = set()
        unique = []
        for t in all_terms:
            if t not in seen:
                seen.add(t)
                unique.append(t)

        unique.sort(key=lambda x: -len(x))
        return unique[:500]

    def get_confusion_dict(self) -> dict:
        return self.confusion_dict

    def get_exam_catalog(self) -> dict:
        return self.exam_catalog

    def match_with_rules(self, see_text: str, hint_text: str) -> list:
        """用knowledge中的规则做匹配"""
        if not see_text and not hint_text:
            return []

        results = []

        # 1. 用模板字段匹配（template_fields.json）
        tf = self.template_fields
        if tf:
            tpl_list = tf.get('templates', tf.get('tpls', []))
            for tpl in tpl_list:
                name = tpl.get('name', '') or tpl.get('DISCNAME', '')
                desc = tpl.get('description', '') or tpl.get('INFO1', '')
                diag = tpl.get('diagnosis', '') or tpl.get('INFO2', '')
                site = tpl.get('site', '') or tpl.get('MODULENAME', '')
                group = tpl.get('group', '') or tpl.get('DISCGROUP', '')

                score = 0.0
                if diag and hint_text and diag in hint_text:
                    score = 1.0
                elif desc and see_text:
                    desc_kws = set(re.findall(r'[一-鿿]{2,}', desc))
                    see_kws = set(re.findall(r'[一-鿿]{2,}', see_text))
                    if desc_kws and see_kws:
                        inter = desc_kws & see_kws
                        score = len(inter) / max(len(desc_kws), 1)

                if score >= 0.15:
                    results.append({
                        'template_id': tpl.get('id', ''),
                        'template_name': name,
                        'score': round(score, 4),
                        'site': site,
                        'discgroup': group,
                        'description': desc[:300],
                        'diagnosis': diag[:200],
                    })

        # 2. 用section_templates_merged.json补充
        st = self.section_templates
        if isinstance(st, dict):
            for tid, tpl in st.items():
                name = tpl.get('name', '') or tpl.get('title', '')
                desc = tpl.get('description', '') or tpl.get('text', '')
                diag = tpl.get('diagnosis', '')
                site = tpl.get('site', '')

                if not name:
                    continue

                desc_clean = re.sub(r'\s+', '', str(desc))
                see_clean = re.sub(r'\s+', '', see_text or '')
                diag_clean = re.sub(r'\s+', '', str(diag))
                hint_clean = re.sub(r'\s+', '', hint_text or '')

                score = 0.0
                if diag_clean and hint_clean and diag_clean in hint_clean:
                    score = 1.0
                elif desc_clean and see_clean:
                    dk = set(re.findall(r'[一-鿿]{2,}', desc_clean))
                    sk = set(re.findall(r'[一-鿿]{2,}', see_clean))
                    if dk and sk:
                        score = len(dk & sk) / max(len(dk), 1)

                if score >= 0.15:
                    results.append({
                        'template_id': tid,
                        'template_name': name,
                        'score': round(score, 4),
                        'site': site,
                        'discgroup': '',
                        'description': desc_clean[:300],
                        'diagnosis': diag_clean[:200],
                    })

        seen_names = set()
        unique_results = []
        for r in sorted(results, key=lambda x: -x['score']):
            if r['template_name'] not in seen_names:
                seen_names.add(r['template_name'])
                unique_results.append(r)

        return unique_results[:10]


# 全局单例
knowledge = KnowledgeEngine()
