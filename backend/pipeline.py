"""
超声语音报告系统 - 自动化处理管线
接收语音文本 → 意图识别 → 模板匹配 → 变量提取 → 报告生成
"""
import re, json, time, uuid
from datetime import datetime
from knowledge_engine import knowledge
from engine import Matcher
from routing_rules import route, detect_site
from database import get_db


class Pipeline:
    """全自动处理管线"""

    def __init__(self, matcher: Matcher):
        self.matcher = matcher

    # ====== 变量提取 ======
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

    # ====== 意图识别 ======
    def detect_intent(self, text: str) -> dict:
        """从文本中识别检查意图"""
        t = re.sub(r'\s+', '', text)
        sites = detect_site(t)

        intent = {
            'sites': list(sites),
            'is_normal': False,
            'keywords': [],
            'measurements': [],
        }

        # 判断是否正常/阴性报告
        normal_kws = ['未见明显异常', '未见异常', '大小正常', '形态规则', '回声均匀', '表面光滑']
        for kw in normal_kws:
            if kw in t:
                intent['is_normal'] = True
                break

        # 提取异常关键词
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

    # ====== 完整管线 ======
    def process(self, voice_text: str, doctor: str = '') -> dict:
        """
        完整管线：ASR修正 → 意图识别 → 路由匹配 → 变量提取 → 报告生成
        """
        start = time.time()

        # 1. ASR修正
        corrected = knowledge.correct_asr_text(voice_text)

        # 2. 意图识别
        intent = self.detect_intent(corrected)

        # 3. 模板匹配
        matches = self.matcher.match(corrected)
        best = matches[0] if matches else None

        # 4. 变量提取
        variables = self.extract_vars(voice_text)
        variables.update(self.extract_vars(corrected))

        # 5. 生成报告内容
        report = {
            'description': best['description'] if best else corrected,
            'diagnosis': best['diagnosis'] if best else '',
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
            'matches_count': len(matches),
            'elapsed_ms': round(elapsed * 1000),
        }

    # ====== 自动写入数据库 ======
    def process_and_save(self, voice_text: str, doctor: str = '') -> dict:
        """处理并自动保存到数据库"""
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


# 全局管线实例
pipeline = None


def init_pipeline(matcher):
    global pipeline
    pipeline = Pipeline(matcher)
    return pipeline
