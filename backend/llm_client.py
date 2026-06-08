"""DeepSeek 结构化提取 — v3 ABCDEF流水线 + 超声模板"""

import json
import os
import re
import time
import logging
from openai import OpenAI
from openai import APIError, APITimeoutError

from templates import match_template as match_tpl_key, TEMPLATES
from template_loader import (
    match_template as match_formal_template,
    match_templates_multi,
    format_template_for_prompt,
    load_templates,
)

from knowledge.loader import get_kb

MAX_RETRIES = 2

# ICD-10 编码表：优先从知识库加载，回退到硬编码
def _load_icd10_map() -> dict:
    try:
        kb = get_kb()
        if hasattr(kb, 'normal_ranges') and kb.normal_ranges:
            icd10_section = kb.normal_ranges.get('icd10_codes', {})
            if icd10_section:
                return icd10_section
    except Exception:
        pass
    return {
    # ===== 消化系统 (K00-K93) =====
    "K76.0": "脂肪肝",
    "K76.8": "肝功能异常",
    "K74.6": "肝硬化",
    "K75.8": "肝实质弥漫性病变",
    "K80.0": "胆囊结石伴急性胆囊炎",
    "K80.1": "胆囊结石伴慢性胆囊炎",
    "K80.2": "胆囊结石",
    "K80.3": "胆管结石",
    "K80.4": "胆总管结石伴胆囊炎",
    "K80.5": "胆总管结石",
    "K81.0": "急性胆囊炎",
    "K81.1": "慢性胆囊炎",
    "K81.9": "胆囊炎",
    "K82.0": "胆囊梗阻",
    "K82.1": "胆囊积液",
    "K82.4": "胆囊胆固醇沉着症",
    "K82.8": "胆囊息肉",
    "K82.9": "胆囊壁毛糙",
    "K83.0": "胆管炎",
    "K83.1": "胆管梗阻",
    "K83.5": "胆管囊肿",
    "K85.0": "急性胰腺炎(水肿型)",
    "K85.1": "急性胰腺炎(胆源性)",
    "K85.9": "急性胰腺炎",
    "K86.1": "慢性胰腺炎",
    "K86.8": "胰腺假性囊肿",
    "K86.9": "胰腺回声增强",
    "K35.8": "急性阑尾炎",
    "K40.9": "腹股沟疝",
    "K44.9": "脐疝",
    "K56.6": "肠梗阻",
    "K57.3": "结肠憩室",
    "K59.0": "便秘",
    "K62.8": "直肠息肉",
    "K65.0": "腹腔积液",
    # 肝脏良性
    "Q44.6": "肝囊肿",
    "Q44.7": "多囊肝",
    "D18.0": "肝血管瘤",
    "D13.4": "肝局灶性结节样增生",
    # 肝脏恶性
    "C22.0": "肝细胞癌",
    "C22.1": "肝内胆管细胞癌",
    "C22.9": "肝癌",

    # ===== 泌尿系统 =====
    "N28.1": "肾囊肿",
    "N20.0": "肾结石",
    "N20.1": "输尿管结石",
    "N20.9": "泌尿系结石",
    "N13.3": "肾积水",
    "N18.1": "慢性肾脏病1期",
    "N18.2": "慢性肾脏病2期",
    "N18.3": "慢性肾脏病3期",
    "N18.4": "慢性肾脏病4期",
    "N18.5": "慢性肾脏病5期",
    "N18.9": "慢性肾病",
    "N19": "肾功能不全",
    "N28.0": "肾实质回声增强",
    "N28.8": "肾错构瘤",
    "D30.0": "肾错构瘤(良性)",
    "Q61.0": "单侧多囊肾",
    "Q61.2": "多囊肾",
    "Q61.9": "肾囊性病变",
    "C64": "肾细胞癌",
    "C65": "肾盂恶性肿瘤",
    # 膀胱/前列腺
    "N30.0": "急性膀胱炎",
    "N30.9": "膀胱炎",
    "N32.8": "膀胱壁增厚",
    "R33": "尿潴留",
    "N40": "前列腺增生",
    "N41.9": "前列腺炎",
    "C67.9": "膀胱肿瘤",
    "C61": "前列腺癌",

    # ===== 妇科 =====
    "D25.0": "子宫粘膜下肌瘤",
    "D25.1": "子宫肌壁间肌瘤",
    "D25.2": "子宫浆膜下肌瘤",
    "D25.9": "子宫肌瘤",
    "N80.0": "子宫腺肌症",
    "N80.1": "卵巢子宫内膜异位囊肿",
    "N80.9": "子宫内膜异位症",
    "N84.0": "子宫内膜息肉",
    "N85.0": "子宫内膜增生",
    "N85.5": "子宫内膜回声不均",
    "N83.0": "卵泡囊肿",
    "N83.1": "黄体囊肿",
    "N83.2": "卵巢囊肿",
    "D27.9": "卵巢畸胎瘤",
    "D27": "卵巢良性肿瘤",
    "N70.0": "急性输卵管炎",
    "N70.1": "输卵管积水",
    "N70.9": "附件炎",
    "N73.6": "盆腔粘连",
    "R10.2": "盆腔积液",
    "C54.1": "子宫内膜癌",
    "C54.9": "子宫体癌",
    "C56": "卵巢癌",
    "C53.9": "宫颈癌",

    # ===== 产科 =====
    "O00.0": "输卵管妊娠",
    "O00.9": "异位妊娠",
    "O01.9": "葡萄胎",
    "O02.0": "枯萎孕囊",
    "O02.1": "稽留流产",
    "O03.9": "难免流产",
    "O04.9": "不全流产",
    "O20.0": "先兆流产",
    "O20.9": "妊娠期出血",
    "O26.8": "妊娠期肝内胆汁淤积",
    "O28.3": "产前超声筛查异常",
    "O30.0": "双胎(单绒毛膜)",
    "O30.1": "双胎(双绒毛膜)",
    "O34.2": "子宫切口憩室",
    "O35.8": "胎儿发育异常",
    "O36.5": "胎儿生长受限",
    "O36.8": "胎儿窘迫",
    "O41.0": "羊水过少",
    "O42.0": "胎膜早破",
    "O44.0": "前置胎盘(完全性)",
    "O44.1": "前置胎盘(部分性)",
    "O44.9": "前置胎盘",
    "O45.0": "胎盘早剥",
    "O45.9": "胎盘早剥(未特指)",
    "O60.0": "早产",
    "O69.8": "脐带绕颈",
    "O80": "足月顺产",
    "P08.0": "大于胎龄儿",

    # ===== 心血管 =====
    "I05.0": "二尖瓣狭窄",
    "I34.0": "二尖瓣关闭不全",
    "I34.1": "二尖瓣脱垂",
    "I34.8": "二尖瓣反流",
    "I35.0": "主动脉瓣狭窄",
    "I35.1": "主动脉瓣关闭不全",
    "I35.2": "主动脉瓣狭窄伴关闭不全",
    "I35.8": "主动脉瓣钙化",
    "I07.0": "三尖瓣狭窄",
    "I07.1": "三尖瓣关闭不全",
    "I07.2": "三尖瓣反流",
    "I10": "原发性高血压",
    "I11.9": "高血压性心脏病",
    "I20.9": "心绞痛",
    "I21.9": "急性心肌梗死",
    "I25.1": "冠心病",
    "I25.2": "陈旧性心肌梗死",
    "I25.5": "缺血性心肌病",
    "I27.0": "原发性肺动脉高压",
    "I27.1": "肺源性心脏病",
    "I27.2": "肺动脉高压",
    "I27.8": "肺动脉增宽",
    "I30.1": "感染性心包炎",
    "I30.9": "急性心包炎",
    "I31.1": "缩窄性心包炎",
    "I31.3": "心包积液",
    "I31.9": "心包增厚",
    "I33.0": "感染性心内膜炎",
    "I42.0": "扩张型心肌病",
    "I42.1": "肥厚型心肌病",
    "I42.2": "肥厚型心肌病(梗阻性)",
    "I42.5": "限制型心肌病",
    "I42.9": "心肌病(未特指)",
    "I44.0": "一度房室传导阻滞",
    "I44.1": "二度房室传导阻滞",
    "I44.2": "三度房室传导阻滞",
    "I48.0": "阵发性心房颤动",
    "I48.1": "持续性心房颤动",
    "I48.9": "心房颤动",
    "I49.5": "病态窦房结综合征",
    "I50.0": "充血性心力衰竭",
    "I50.1": "左心衰竭",
    "I50.9": "心力衰竭",
    "I51.7": "心脏扩大",
    "I51.8": "左室壁运动异常",
    "I51.9": "心功能不全",
    "I63.9": "脑梗死",
    "I65.2": "颈动脉狭窄",
    "I67.2": "脑动脉粥样硬化",
    "I70.0": "主动脉粥样硬化",
    "I70.2": "下肢动脉粥样硬化",
    "I71.0": "主动脉夹层",
    "I71.4": "腹主动脉瘤",
    "I71.9": "主动脉瘤",
    "I73.9": "外周血管病变",
    "I74.3": "下肢动脉闭塞",
    "I80.2": "下肢深静脉血栓",
    "I80.3": "下肢静脉血栓",
    "I81": "门静脉血栓",
    "I83.0": "下肢静脉曲张伴溃疡",
    "I83.9": "下肢静脉曲张",
    "I87.1": "精索静脉曲张",
    # 先天性心脏病
    "Q21.0": "室间隔缺损",
    "Q21.1": "房间隔缺损",
    "Q21.2": "房室间隔缺损",
    "Q21.3": "法洛四联症",
    "Q23.0": "先天性主动脉瓣狭窄",
    "Q23.1": "先天性主动脉瓣关闭不全",
    "Q23.2": "先天性二尖瓣狭窄",
    "Q23.3": "先天性二尖瓣关闭不全",
    "Q24.0": "右位心",
    "Q25.0": "动脉导管未闭",
    "Q25.1": "主动脉缩窄",
    "Q25.6": "肺动脉狭窄",
    "D15.1": "左心房粘液瘤",

    # ===== 内分泌/甲状腺 =====
    "E03.9": "甲状腺功能减退",
    "E04.0": "非毒性单结节甲状腺肿",
    "E04.1": "甲状腺结节",
    "E04.2": "非毒性多结节甲状腺肿",
    "E04.9": "非毒性甲状腺肿",
    "E05.0": "甲亢(Graves病)",
    "E05.1": "毒性甲状腺结节",
    "E05.2": "毒性多结节甲状腺肿",
    "E05.9": "甲状腺功能亢进",
    "E06.0": "急性甲状腺炎",
    "E06.1": "亚急性甲状腺炎",
    "E06.3": "桥本氏甲状腺炎",
    "E06.5": "慢性甲状腺炎",
    "E06.9": "甲状腺炎",
    "E07.8": "甲状腺回声减低",
    "E07.9": "甲状腺弥漫性病变",
    "E11.9": "2型糖尿病",
    "E21.0": "甲状旁腺腺瘤",
    "E21.1": "继发性甲状旁腺功能亢进",
    "E21.9": "甲状旁腺功能亢进",
    "E28.2": "多囊卵巢综合征",
    "C73": "甲状腺癌",
    "D34": "甲状腺腺瘤",

    # ===== 乳腺 =====
    "N60.0": "乳腺孤立性囊肿",
    "N60.1": "乳腺增生(弥漫性囊性乳腺病)",
    "N60.2": "乳腺纤维囊性病",
    "N60.3": "乳腺纤维硬化症",
    "N60.9": "乳腺纤维腺瘤",
    "N61": "乳腺炎",
    "N62": "男性乳房发育",
    "N63": "乳腺肿块",
    "N64.4": "乳腺痛",
    "N64.8": "乳腺导管扩张",
    "D24": "乳腺良性肿瘤",
    "C50.0": "乳腺癌(乳头/乳晕)",
    "C50.1": "乳腺癌(中央部)",
    "C50.2": "乳腺癌(内上象限)",
    "C50.3": "乳腺癌(内下象限)",
    "C50.4": "乳腺癌(外上象限)",
    "C50.5": "乳腺癌(外下象限)",
    "C50.9": "乳腺癌",
    # 淋巴
    "R59.0": "颈部淋巴结肿大",
    "R59.1": "全身淋巴结肿大",
    "R59.9": "淋巴结肿大",
    "I88.0": "肠系膜淋巴结炎",
    "I88.9": "淋巴结炎",
    # 骨骼
    "M17.9": "膝关节退行性变",
    "M47.9": "脊柱退行性变",
    "M51.2": "腰椎间盘突出",
    "M51.8": "腰椎间盘病变",
    # 脾脏
    "R16.1": "脾大",
    "D73.4": "脾囊肿",
    "Q89.0": "副脾",
    # 腹水/积液
    "R18": "腹水",
    # 其他常见
    "Q89.2": "甲状舌管囊肿",
    "L72.0": "表皮样囊肿",
    "L72.1": "皮脂腺囊肿",
    "K11.2": "腮腺炎",
    "K11.5": "腮腺肿大",
    "K11.8": "腮腺肿块",
    "C07": "腮腺恶性肿瘤",
    "D11.0": "腮腺良性肿瘤",
    "R19.0": "腹腔肿块",
    "R22.0": "颈部肿块",
    "R22.9": "体表肿块",
    "C62.9": "睾丸肿瘤",
    "N43.3": "睾丸鞘膜积液",
    "N44": "睾丸扭转",
    "N45.9": "附睾炎",
    "D17.9": "脂肪瘤",
    "D21.9": "软组织良性肿瘤",
    "Z00.0": "健康查体",
    "Z01.8": "体检发现异常",
}

ICD10_MAP = _load_icd10_map()

# 确保模板已加载
load_templates()


def _get_client(provider: str = "deepseek"):
    if provider == "volc":
        return OpenAI(
            api_key="ark-70272cfb-cdc5-42f4-bb67-e8e721557010-bf3e6",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        )
    if provider == "dashscope":
        # 优先环境变量，其次本地 .env
        _key = os.getenv("DASHSCOPE_API_KEY")
        if not _key:
            try:
                from dotenv import load_dotenv
                from pathlib import Path
                _p = Path(__file__).resolve().parent.parent.parent / ".env"
                if _p.exists():
                    load_dotenv(_p)
                    _key = os.getenv("DASHSCOPE_API_KEY")
            except Exception:
                pass
        return OpenAI(
            api_key=_key or "",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1",
    )


def _system_prompt(exam_type: str, formal_tpl: dict | None = None) -> str:
    tpl_key = match_tpl_key(exam_type)
    tpl = TEMPLATES.get(tpl_key, TEMPLATES["abdomen"])

    # 正式模板参考
    formal_ref = ""
    if formal_tpl:
        formal_ref = f"""
## 正式模板参考（请按此格式输出）

{format_template_for_prompt(formal_tpl)}
"""

    return f"""你是一位资深超声科主任医师。将口语化的超声检查口述转换为规范化超声报告。

当前检查类型: {tpl["name"]}
覆盖脏器: {"、".join(tpl["organs"])}
{formal_ref}
## Few-Shot 参考案例（请严格模仿以下输出格式和术语规范）

【案例1: 正常腹部体检】
口述: "肝脏大小形态正常，包膜光滑，实质回声均匀。胆囊大小约68乘28毫米，壁光滑。"
输出: {{"study_see": "肝脏: 大小形态正常，包膜光滑，实质回声均匀。\\n胆囊: 大小约68×28mm，囊壁光滑，腔内未见异常回声。\\n胰腺: 大小形态正常。\\n脾脏: 未见肿大。\\n双肾: 大小形态正常。", "study_hint": [{{"rank": 1, "diagnosis": "腹部超声检查未见明显异常", "icd10": ""}}], "recommendation": "建议定期体检复查。"}}

【案例2: 脂肪肝+胆囊息肉】
口述: "肝脏体积稍大，回声增强增粗，肝肾反差明显。胆囊壁上见一约0.4乘0.3cm高回声团，附壁。"
输出: {{"study_see": "肝脏: 体积稍增大，实质回声增强增粗，肝肾反差明显，符合脂肪肝声像图改变。\\n胆囊: 大小正常，壁上可见一大小约0.4×0.3cm高回声团，附壁，后方无声影，考虑胆囊息肉。\\n胰腺: 大小形态正常。\\n脾脏: 未见肿大。\\n双肾: 大小形态正常。", "study_hint": [{{"rank": 1, "diagnosis": "脂肪肝", "icd10": "K76.0 脂肪肝"}}, {{"rank": 2, "diagnosis": "胆囊息肉", "icd10": "K82.8 胆囊息肉"}}], "recommendation": "建议低脂饮食，6个月后复查。"}}

【案例3: 胆囊结石】
口述: "胆囊大小约70乘30毫米，壁厚3毫米，毛糙，囊内见多个强回声团，一个约8乘6毫米，后伴声影，随体位移动。"
输出: {{"study_see": "肝脏: 大小形态正常。\\n胆囊: 大小约70×30mm，壁厚3mm，毛糙，囊内见多个强回声团，其中一个约8×6mm，后伴声影，随体位移动。\\n胰腺: 大小形态正常。\\n脾脏: 未见肿大。\\n双肾: 大小形态正常。", "study_hint": [{{"rank": 1, "diagnosis": "胆囊结石", "icd10": "K80.2 胆囊结石"}}], "recommendation": "建议肝胆外科就诊。"}}

【案例4: 湘普口音纠错 — 肝囊肿】
口述: "肝脏里面看到一个小水泡一样的东西，大概15乘12毫米，边界清楚，后面回声增强。胆囊没啥问题。"
输出: {{"study_see": "肝脏: 大小形态正常，肝内可见一个大小约15×12mm的无回声区，边界清晰，后方回声增强，考虑肝囊肿。\\n胆囊: 大小正常，囊壁光滑，腔内未见异常回声。\\n胰腺: 大小形态正常。\\n脾脏: 未见肿大。\\n双肾: 大小形态正常。", "study_hint": [{{"rank": 1, "diagnosis": "肝囊肿", "icd10": "Q44.6 肝囊肿"}}], "recommendation": "建议定期复查。"}}

【案例5: 心脏 — 湘普纠错】
口述: "心脏做得不太好，左边扩大了约68毫米，心肌收缩没力气，EF只有35%。二尖瓣关不紧，有中度反流。心包里没有水。"
输出: {{"study_see": "左心室增大，舒张末期内径约68mm。左室壁运动弥漫性减弱，EF约35%。二尖瓣可见中度反流。心包腔内未见液性暗区。", "study_hint": [{{"rank": 1, "diagnosis": "扩张型心肌病", "icd10": "I42.0 扩张型心肌病"}}, {{"rank": 2, "diagnosis": "心力衰竭", "icd10": "I50.9 心力衰竭"}}], "recommendation": "建议心内科积极治疗。"}}

## 湘普/南方口音 → 标准术语 纠错规则（方言适配）
- "小水泡"/"水泡" → "无回声区"或"囊肿"
- "时值回声" → "实质回声"
- "做得不太好" → （转换为专业报告语言，保留核心事实）
- "关不紧" → "关闭不全"/"反流"
- "没力气"/"没劲" → "运动减弱"
- "没有水" → "未见积液"
- "好像"/"还行" → （去掉口语化，保留核心事实）
- "没啥问题"/"没事" → "未见异常"
- "大一点点"→"稍增大", "小一点点"→"稍缩小"
- "乘" → "×"
- "冇"/"冇得"/"冇半点" → "未见"/"没有" (方言)
- "噻"/"啰"/"啵"/"哒" → 删除语气词 (方言句末语气词)
- "筐瓢" → "测量错误需重新测量" (方言:搞砸了)
- "没得劲"/"不得劲" → "运动减弱"
- "关不严实" → "关闭不全"
- "干净"/"透亮" → "未见异常回声" (方言:干净=没问题)
- "蛮好" → "正常"
- "不大对头"/"有点事" → "异常发现"

## 规则
1. 口述中缺失的测量值填"___mm"占位，绝不编造数值
2. 口语转标准术语（参考上述纠错规则）
3. study_see 按脏器分段，每段格式: "脏器名: 描述。"
4. study_hint 每条一行，按临床重要性排序，只列阳性发现。全部正常时输出"X检查未见明显异常", ICD-10填"Z00.0 健康查体(未见异常)"
5. study_hint 标注 ICD-10 编码+名称（格式 "K76.0 脂肪肝"）。正常报告必须填 "Z00.0 健康查体(未见异常)"
6. 口述中提及的每一个脏器都在 study_see 中出现（包括正常脏器）
7. patient_info 全部填 null
8. 只输出 JSON，不要任何解释文字
9. 数值中的中文"乘"统一转换为标准符号"×"
10. 【阳性直充阴性全自动】医生只说阳性/异常发现, 未提及的脏器/指标自动填入正常描述。例: 腹部模板, 医生只说"胆囊结石5mm", AI自动填肝/胰/脾/肾=正常。
11. 【BI-RADS/TI-RADS 实时分级】根据口述特征自动计算分级:
    TI-RADS: 低回声+1分、边界不清+1分、纵横比>1+3分、微钙化+3分 → 自动输出TR等级+恶性风险%
    BI-RADS: 形态不规则+边界模糊+血流丰富=4b类 → 自动提示"建议穿刺活检"
12. 【尺寸自动规整】所有口语尺寸归一化为标准格式:
    "两公分乘13毫米" → "20×13mm"
    "23 12 15 毫米" → "23×12×15mm"
    "1.5的囊" → "大小约15mm的囊性区"
    "不到1mm" → "约1mm"
13. 【语音指令拦截】口述文本如果完全匹配以下指令, 不调用LLM, 直接返回 command 类型:
    "清空重来" → {"type":"command","command":"CLEAR"}
    "保存报告" → {"type":"command","command":"SAVE"}
    "下一项" → {"type":"command","command":"NEXT"}
14. 【语义级擦除】医生改口/纠错时自动理解意图:
    "不对,上一句改掉,肝脏今天还没看" → 删除肝脏相关描述
    "脾脏大小刚才不对,重新报42mm" → 修正脾脏数据
    "不是肝脏,我看的是脾脏" → 交换器官归属
    "把刚才的肝脏数据擦掉" → 清空肝脏字段
15. 【历史随访对比】如果系统提供了"上次检查记录", 请在 recommendation 中自动输出对比结论:
    结节增大→"该结节较上次(2025-06)增大X%, 建议密切随访或穿刺"
    结节缩小→"结节较上次缩小X%, 继续观察"
    新发结节→"本次新发现结节, 建议3个月后复查确认"
    无变化→"与上次检查相比无明显变化"
16. 【医保DRGs/DIP合规术语规范化】所有诊断和ICD-10编码必须使用国家医保标准术语:
    - 诊断描述使用标准疾病全称, 避免口语缩写
    - ICD-10编码与诊断一一对应, 格式: "K76.000 非酒精性脂肪性肝炎(重度)"
    - 禁止使用 "可能性大"、"考虑"、"不除外" 等不确定术语(易被医保拒付)
    - 多个诊断按临床重要性排序, 主诊断在前(关联DRG分组权重)
17. 【大白话患者解读】在JSON中增加 "patient_note" 字段:
    - 用温暖亲切的语气将专业结论翻译成通俗易懂的文字
    - 格式: "【AI健康小贴士】：[性别称呼]您好，..."
    - 良性 → 安抚语气, 告诉患者不用担心
    - 恶性/可疑 → 建议就医但不制造恐慌
    - 含复查建议 + 健康生活提示
18. 【声控影像调节】识别以下语音指令(不计费):
    "放大两倍"/"调亮一点"/"左边对比"/"冻结图像"/"截图保存"

## 输出 JSON Schema
{{
  "patient_info": {{ "name": null, "gender": null, "age": null, "exam_id": null }},
  "exam_info": {{ "modality": "{tpl["name"]}", "device": null, "exam_date": null }},
  "study_see": "脏器分段描述。每段格式: 脏器名: 描述。",
  "study_hint": [
    {{ "rank": 1, "diagnosis": "疾病名", "icd10": "标准ICD-10编码 (医保合规)" }}
  ],
  "recommendation": "建议文字 (含随访对比结论)",
  "patient_note": "【AI健康小贴士】：用大白话向患者解释检查结果, 安抚语气, 含健康建议"
}}"""


def _extract_json(content: str) -> str:
    content = content.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if m:
        return m.group(1).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return content[start: end + 1]
    return content


def _parse_json(content: str) -> dict:
    json_str = _extract_json(content)
    errors = []

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        errors.append(f"直接解析: {e}")

    try:
        fixed = json_str.rstrip()
        open_braces = fixed.count("{") - fixed.count("}")
        open_brackets = fixed.count("[") - fixed.count("]")
        in_string = fixed.count('"') % 2 != 0
        if in_string:
            fixed += '"'
        fixed += "]" * open_brackets + "}" * open_braces
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        errors.append(f"补全括号: {e}")

    lines = json_str.split("\n")
    for cut in range(1, min(5, len(lines))):
        try:
            return _parse_json("\n".join(lines[:-cut]))
        except Exception:
            pass

    raise ValueError(f"JSON 解析失败: {'; '.join(errors)}")


def _enrich_icd10(report: dict) -> dict:
    for imp in report.get("study_hint", []):
        icd10 = imp.get("icd10", "") or ""
        if not icd10.strip():
            continue
        code_only = icd10.strip().split()[0]
        name = ICD10_MAP.get(code_only, "")
        if name and name not in icd10:
            imp["icd10"] = f"{code_only} {name}"
    return report


def structure_report(raw_text: str, exam_type: str = "腹部超声") -> dict:
    """结构化提取：输出 study_see + study_hint 双层格式"""
    client = _get_client()

    # P0-2: 匹配正式模板
    formal_tpl = match_formal_template(raw_text, exam_type)

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[
                    {"role": "system", "content": _system_prompt(exam_type, formal_tpl)},
                    {"role": "user", "content": (
                        f"请将以下{exam_type}检查口述转换为规范化超声报告"
                        f"（注意：study_see 必须包含口述中提到的每一个脏器）：\n\n{raw_text}"
                    )},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("DeepSeek 返回空内容")

            report = _parse_json(content)
            report = _enrich_icd10(report)
            return report

        except (APIError, APITimeoutError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                import time
                time.sleep(1.5 ** attempt)
                continue
            raise RuntimeError(f"DeepSeek API 调用失败(已重试{MAX_RETRIES}次): {e}") from e

        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"结构化输出解析失败: {e}") from e

    raise RuntimeError(f"结构化失败: {last_error}")


def _extract_plain_text(html_or_text: str) -> str:
    text = re.sub(r'<[^>]+>', '', html_or_text or "")
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


_log = logging.getLogger(__name__)


def generate_free_report(asr_text: str, exam_type: str = "腹部超声") -> dict:
    client = _get_client()
    system = f"""一位资深超声科主任医师，将口语化口述转为规范化超声报告。
检查类型: {exam_type}

## Few-Shot参考(严格模仿):
案例1: 口述"肝脏大小正常，胆囊68乘28毫米，壁光滑" → JSON: {{"study_see":"肝脏: 大小形态正常。胆囊: 大小约68×28mm，囊壁光滑。胰腺: 正常。脾脏: 未见肿大。双肾: 正常。","study_hint":[{{"rank":1,"diagnosis":"腹部超声未见明显异常","icd10":""}}],"recommendation":"定期体检。"}}
案例2: 口述"肝脏回声增强，肝肾反差明显，胆囊壁上0.4乘0.3cm高回声附壁" → JSON: {{"study_see":"肝脏: 实质回声增强增粗，肝肾反差明显，符合脂肪肝。胆囊: 壁上可见大小约0.4×0.3cm高回声团，附壁，考虑胆囊息肉。","study_hint":[{{"rank":1,"diagnosis":"脂肪肝","icd10":"K76.0 脂肪肝"}},{{"rank":2,"diagnosis":"胆囊息肉","icd10":"K82.8 胆囊息肉"}}],"recommendation":"低脂饮食，6个月复查。"}}

## 湘普口音纠错:
小水泡→无回声区/囊肿, 乘→×, 关不紧→关闭不全, 没力气→运动减弱, 没有水→未见积液, 没啥问题→未见异常, 时值回声→实质回声

## 规则: 缺失值填___mm，口语转术语，按脏器分段，每个脏器都出现（包括正常）。只输出JSON。
输出格式: {{"study_see":"...", "study_hint":[...], "recommendation":"..."}}"""

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat", messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"请将以下口述转为规范化报告:\n\n{asr_text}"},
                ], temperature=0.1, max_tokens=4096)
            content = response.choices[0].message.content
            if not content: raise RuntimeError("empty")
            r = _parse_json(content)
            r["_method"] = "b_free_gen"
            return r
        except Exception as e:
            if attempt < 1: time.sleep(1.0); continue
            _log.warning(f"B fail: {e}")
    return {"study_see": f"<div class='rpt-html'>{asr_text}</div>", "study_hint": [], "recommendation": "", "_method": "b_fallback"}


def select_and_fill_template(asr_text: str, b_result: dict | None, c_result: dict | None,
                              d_result: dict | None, exam_type: str, candidates: list[dict]) -> dict:
    from template_loader import get_template_by_name
    client = _get_client()

    cand_parts = []
    for c in candidates[:8]:
        tpl = get_template_by_name(c["name"])
        if tpl: cand_parts.append(f"### {c['name']} (模块:{c.get('module','')})\n{tpl.get('info1','')[:500]}")
    cand_text = "\n\n".join(cand_parts)

    b_see = _extract_plain_text(b_result.get("study_see", ""))[:500] if b_result else "(无)"
    b_hint = json.dumps(b_result.get("study_hint", []), ensure_ascii=False)[:300] if b_result else "[]"
    c_see = _extract_plain_text(c_result.get("study_see", ""))[:500] if c_result else "(无)"
    c_hint = json.dumps(c_result.get("study_hint", []), ensure_ascii=False)[:300] if c_result else "[]"
    d_see = _extract_plain_text(d_result.get("study_see", ""))[:500] if d_result else "(无)"
    d_hint = json.dumps(d_result.get("study_hint", []), ensure_ascii=False)[:300] if d_result else "[]"

    system = f"""资深超声科主任医师。检查类型: {exam_type}。从候选模板中选最优，填入测量值。

## Few-Shot参考(严格模仿格式):
案例: 口述"肝脏形态饱满，回声增强增粗，肝肾反差明显" → 选模板"脂肪肝" → 输出JSON: {{"template_name":"脂肪肝", "filled_study_see_html":"肝脏形态饱满，实质回声增强增粗，肝肾反差明显，符合脂肪肝声像图改变。", "study_hint":[{{"rank":1,"diagnosis":"脂肪肝","icd10":"K76.0 脂肪肝"}}],"recommendation":"建议低脂饮食，6个月复查。","confidence":0.9}}

## 规则:
- 模板中 "mm" 替换为实际值(如"5.2mm")
- "[选项A;选项B]" 选一个
- 缺失值保留 "___mm"
- 乘→×, 小水泡→无回声区, 湘普口音按医学术语规范处理
- 用 <b class="voice">值</b> 标记AI填充
- 只输出JSON: {{"template_name":"...", "filled_study_see_html":"...", "study_hint":[...], "recommendation":"...", "confidence":0.85}}"""

    user_msg = f"""## ASR(A路)\n{asr_text[:600]}\n## B路\nstudy_see: {b_see}\nstudy_hint: {b_hint}\n## C路\nstudy_see: {c_see}\nstudy_hint: {c_hint}\n## D路\nstudy_see: {d_see}\nstudy_hint: {d_hint}\n## 候选模板\n{cand_text}"""

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat", messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ], temperature=0.1, max_tokens=4096)
            content = response.choices[0].message.content
            if not content: raise RuntimeError("empty")
            r = _parse_json(content)
            r["_method"] = "e_template_select"
            return r
        except Exception as e:
            if attempt < 1: time.sleep(1.0); continue
            _log.warning(f"E fail: {e}")

    if candidates:
        tpl = get_template_by_name(candidates[0]["name"])
        return {"template_name": candidates[0]["name"],
                "filled_study_see_html": tpl.get("info1","") if tpl else (c_result.get("study_see","") if c_result else ""),
                "study_hint": c_result.get("study_hint",[]) if c_result else [],
                "recommendation": "", "confidence": 0.3, "_method": "e_fallback"}
    return {"template_name": "未知", "filled_study_see_html": c_result.get("study_see","") if c_result else "",
            "study_hint": [], "recommendation": "", "confidence": 0.1, "_method": "e_fallback"}


# ── EF合并: v4-flash 一次完成模板选择+填充+交叉验证 ──

def _ef_combined_system_prompt(exam_type: str) -> str:
    return f"""资深超声科主任医师，完成超声报告的模板选择、变量填充和最终审核。检查类型: {exam_type}

## Few-Shot 参考案例（请严格模仿以下输出格式和术语规范）

案例1(正常腹部): 口述"肝脏大小形态正常，包膜光滑。胆囊68乘28毫米，壁光滑。" → "肝脏: 大小形态正常，包膜光滑，实质回声均匀。胆囊: 大小约68×28mm，囊壁光滑。"
案例2(脂肪肝): 口述"肝脏回声增强增粗，肝肾反差明显。胆囊壁上0.4乘0.3cm高回声团附壁。" → "肝脏: 实质回声增强增粗，肝肾反差明显，符合脂肪肝。胆囊息肉。"
湘普纠错: "小水泡"→"无回声区/囊肿", "乘"→"×", "关不紧"→"关闭不全", "没力气"→"运动减弱", "没有水"→"未见积液", "没啥问题"→"未见异常"

## 你的4项任务 (按顺序)

### 1. 选模板
从候选模板列表中选出最匹配ASR原文的一条

### 2. 填变量 (关键: 尽可能填充所有mm占位符!)
- 模板中每一个 "mm" 处都必须填入实际数值，即便是从上下文中推断的大约值
- "[选项A;选项B;选项C]" → 只保留一个正确选项
- 实在缺失的填 "未测" 或保留 "__mm" (尽量少用)
- 用 <b class="voice">值</b> 标记AI填充值(绿色), 未填写用 <i class="unfill">__</i> 标记(橙色)
- [选项A;选项B;选项C] → 语音命中的选项用 <b class="voice">选项</b> 绿色标记

### 3. 交叉验证
对比所有来源(B自由生成/C规则引擎/D规则增强)，标记冲突并选择最可靠的值

### 4. 不改变模板结构
段落、标题、标点、顺序一律不动

## 输出JSON
{{"template_name":"...", "filled_study_see_html":"...", "study_hint":[...], "recommendation":"...", "confidence":0.9, "conflicts":[{{"field":"...", "sources":{{}}, "resolution":"..."}}], "reasoning":"..."}}"""


def select_fill_and_validate(
    asr_text: str, b_result: dict | None, c_result: dict | None,
    d_result: dict | None, exam_type: str, candidates: list[dict],
) -> dict:
    """EF合并: 一次v4-flash调用完成模板选择+填充+交叉验证"""
    from template_loader import get_template_by_name
    from rule_engine import get_rule
    client = _get_client()

    # 加载字段ASR提示词，注入到system prompt中帮助v4-flash精准匹配
    field_hints = get_rule("extraction.field_asr_hints", {})
    hints_text = ""
    if field_hints:
        hint_parts = []
        for field_id, info in list(field_hints.items())[:20]:
            kwds = "、".join(info.get("keywords", [])[:4])
            unit = info.get("unit", "")
            rng = info.get("range", [])
            hint_parts.append(f"- {field_id}: 搜索\"{kwds}\" 单位{unit} 范围{rng}")
        hints_text = "\n## 字段ASR搜索提示\n" + "\n".join(hint_parts)

    cand_parts = []
    for c in candidates[:8]:
        tpl = get_template_by_name(c["name"])
        if tpl:
            cand_parts.append(f"### {c['name']} (模块:{c.get('module','')})\n{tpl.get('info1','')[:500]}")
    cand_text = "\n\n".join(cand_parts)

    b_see = _extract_plain_text(b_result.get("study_see", ""))[:400] if b_result else "(无)"
    b_hint = json.dumps(b_result.get("study_hint", []), ensure_ascii=False)[:200] if b_result else "[]"
    c_see = _extract_plain_text(c_result.get("study_see", ""))[:400] if c_result else "(无)"
    c_hint = json.dumps(c_result.get("study_hint", []), ensure_ascii=False)[:200] if c_result else "[]"
    d_see = _extract_plain_text(d_result.get("study_see", ""))[:400] if d_result else "(无)"
    d_hint = json.dumps(d_result.get("study_hint", []), ensure_ascii=False)[:200] if d_result else "[]"

    user_msg = f"""## ASR(A路)\n{asr_text[:500]}\n## B路(自由生成)\nsee: {b_see}\nhint: {b_hint}\n## C路(规则引擎)\nsee: {c_see}\nhint: {c_hint}\n## D路(规则增强)\nsee: {d_see}\nhint: {d_hint}\n## 候选模板\n{cand_text}{hints_text}"""

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat", messages=[
                    {"role": "system", "content": _ef_combined_system_prompt(exam_type)},
                    {"role": "user", "content": user_msg},
                ], temperature=0.1, max_tokens=4096)
            content = response.choices[0].message.content
            if not content: raise RuntimeError("empty")
            r = _parse_json(content)
            r["_method"] = "ef_combined"
            return r
        except Exception as e:
            if attempt < 1: time.sleep(1.0); continue
            _log.warning(f"EF combined fail: {e}")

    # Fallback to C result
    return {
        "template_name": candidates[0]["name"] if candidates else "未知",
        "filled_study_see_html": c_result.get("study_see", "") if c_result else f"<div class='rpt-html'>{asr_text}</div>",
        "study_hint": c_result.get("study_hint", []) if c_result else [],
        "recommendation": "", "confidence": 0.3, "conflicts": [],
        "reasoning": "EF回退到规则引擎", "_method": "ef_fallback",
    }


def arbitrate_report(asr_text, rule_result, llm_result, exam_type="腹部超声"):
    return select_and_fill_template(asr_text, llm_result, rule_result, None, exam_type, [])
