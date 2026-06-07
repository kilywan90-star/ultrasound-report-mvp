"""
超声语音报告系统 - 自动化处理管线 v2 (LLM增强版)
接收语音文本 → ASR修正 → 意图识别 → 模板匹配(LLM+关键词) → 变量提取 → LLM填充 → 报告生成
"""
import re, json, time, uuid
from datetime import datetime
from knowledge_engine import knowledge
from engine import Matcher
from routing_rules import route, detect_site
from database import get_db


class Pipeline:
    """全自动处理管线 (LLM增强版)"""

    def __init__(self, matcher: Matcher):
        self.matcher = matcher

    EXTRACTORS = [
        ('尺寸_长x宽', r'(\d+\.?\d*)\s*[xX×乘]\s*(\d+\.?\d*)(?:\s*[xX×乘]\s*(\d+\.?\d*))?\s*mm'),
        ('尺寸_mm', r'(\d+\.?\d*)\s*mm'),
        ('百分比', r'(\d+\.?\d*)\s*%'),
        ('血流速度', r'(\d+\.?\d*)\s*(cm/s|m/s)'),
        ('程度', r'(轻|中|重)\s*度?'),
        ('位置', r'(左|右|双侧|前|后)'),
    ]

    def extract_vars(self, text: str) -> dict:
        result = {}
        for name, pat in self.EXTRACTORS:
            m = re.findall(pat, text)
            if m:
                result[name] = m
        return result

    def detect_intent(self, text: str) -> dict:
        t = re.sub(r'\s+', '', text)
        sites = detect_site(t)
        intent = {
            'sites': list(sites),
            'is_normal': False,
            'keywords': [],
            'measurements': [],
        }
        normal_kws = ['未见明显异常', '未见异常', '大小正常', '形态规则', '回声均匀', '表面光滑']
        for kw in normal_kws:
            if kw in t:
                intent['is_normal'] = True
                break
        abnormal_signs = {
            '结石': ['结石', '强回声团', '强光团', '伴声影'],
            '囊肿': ['囊肿', '无回声区', '囊性'],
            '增生': ['增生', '增厚', '增大', '肥大'],
            '斑块': ['斑块', '毛糙', '增厚'],
            '返流': ['返流', '返流血彩'],
            '钙化': ['钙化', '强回声斑', '强回声点'],
            '积液': ['积液', '液暗区', '分离', '积水'],
            '结节': ['结节', '低回声', '混合回声'],
            '肌瘤': ['肌瘤'],
        }
        detected = []
        for name, kws in abnormal_signs.items():
            if any(kw in t for kw in kws):
                detected.append(name)
        intent['findings'] = detected
        return intent

    def process(self, voice_text: str, doctor: str = '') -> dict:
        """
        完整管线 v2: ASR修正 → 意图识别 → 模板匹配(LLM+关键词) → 变量提取 → LLM填充
        LLM调用已从4次合并为1次（analyze_and_match输出含规范化+匹配+诊断）
        只有模板填充需要额外1次API（可选）
        """
        start = time.time()
        corrected = knowledge.correct_asr_text(voice_text)
        intent = self.detect_intent(corrected)

        # 模板匹配（引擎内: 关键词→LLM(1次API)→knowledge→路由）
        matches = self.matcher.match(corrected)
        best = matches[0] if matches else None

        # 变量提取
        variables = self.extract_vars(voice_text)
        variables.update(self.extract_vars(corrected))

        # 从LLM匹配结果中读取预生成的诊断和规范化文本
        llm_diagnosis = getattr(self.matcher, '_llm_diagnosis', '')
        llm_normalized = getattr(self.matcher, '_llm_normalized_text', '')

        # LLM模板填充占位符（仅1次API，诊断已由analyze_and_match生成）
        filled_description = ''
        if best and best.get('description') and not filled_description:
            try:
                from llm_engine import llm_fill_template
                filled = llm_fill_template(best['description'], corrected, best.get('template_name', ''))
                if filled and filled != best['description']:
                    filled_description = filled
            except:
                pass

        report = {
            'description': filled_description or (best['description'] if best else corrected),
            'diagnosis': llm_diagnosis or (best['diagnosis'] if best else ''),
            'template_name': best['template_name'] if best else '',
            'template_id': best['template_id'] if best else '',
            'match_score': best['score'] if best else 0,
            'matched_sites': ','.join(intent['sites']),
            'variables': json.dumps(variables, ensure_ascii=False),
            'voice_text': voice_text,
            'corrected_text': corrected,
        }

        elapsed = time.time() - start
        return {
            'report': report,
            'intent': intent,
            'matches': matches,
            'matches_count': len(matches),
            'elapsed_ms': round(elapsed * 1000),
        }

    def process_and_save(self, voice_text: str, doctor: str = '') -> dict:
        result = self.process(voice_text, doctor)
        r = result['report']
        rid = 'AUTO-' + datetime.now().strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:4].upper()
        conn = get_db()
        conn.execute("""INSERT INTO reports(id,doctor,voice_text,template_id,template_name,
                        description,diagnosis,match_score,matched_sites,variables,status)
                        VALUES(?,?,?,?,?,?,?,?,?,?,'draft')""",
                     (rid, doctor, r['voice_text'], r['template_id'], r['template_name'],
                      r['description'], r['diagnosis'], r['match_score'],
                      r['matched_sites'], r['variables']))
        conn.commit()
        conn.close()
        result['report_id'] = rid
        return result


pipeline = None


def init_pipeline(matcher):
    global pipeline
    pipeline = Pipeline(matcher)
    return pipeline
