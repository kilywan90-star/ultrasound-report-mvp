"""
超声语音报告系统 - 自动管线路由器 (v3.0)
"""
from fastapi import APIRouter, HTTPException
from models import MatchQuery
from database import get_db
from pipeline import pipeline
import json

router = APIRouter(prefix="/api/auto", tags=["自动管线"])

@router.post("/process")
def auto_process(q: MatchQuery):
    if not pipeline: raise HTTPException(500, "管线未初始化")
    if not q.text.strip(): raise HTTPException(400, "输入为空")
    result = pipeline.process_and_save(q.text, q.doctor)
    return result

@router.post("/match")
def auto_match(q: MatchQuery):
    if not pipeline: raise HTTPException(500, "管线未初始化")
    result = pipeline.process(q.text, q.doctor)
    return result

@router.get("/intent")
def analyze_intent(text: str):
    if not pipeline: raise HTTPException(500, "管线未初始化")
    result = pipeline.process(text)
    return {"intent": result['intent'], "corrected_text": result['report']['corrected_text']}

@router.post("/batch")
def auto_batch(items: list = []):
    if not pipeline: raise HTTPException(500, "管线未初始化")
    results = []
    for item in items:
        text = item.get('text', '') if isinstance(item, dict) else ''
        doctor = item.get('doctor', '') if isinstance(item, dict) else ''
        if not text: continue
        try:
            results.append(pipeline.process_and_save(text, doctor))
        except:
            results.append({"error": f"处理失败: {text[:30]}"})
    return {"processed": len(results), "results": results}

@router.get("/cheatsheet")
def get_cheatsheet():
    data = [
        {"site":"肝脏","say":"肝脏大小正常，表面光滑，回声均匀","tpl":"正常肝脏（腹部全套）"},
        {"site":"肝脏","say":"肝内有囊肿","tpl":"肝囊肿（单发）"},
        {"site":"肝脏","say":"肝内有多个囊肿","tpl":"肝多发囊肿"},
        {"site":"肝脏","say":"脂肪肝","tpl":"脂肪肝"},
        {"site":"肝脏","say":"轻度脂肪肝","tpl":"脂肪肝（轻度）"},
        {"site":"肝脏","say":"中重度脂肪肝","tpl":"脂肪肝（中-重）"},
        {"site":"肝脏","say":"肝脏脂肪沉积","tpl":"肝脏脂肪沉积(xy)"},
        {"site":"肝脏","say":"肝内有钙化灶","tpl":"肝内钙化灶"},
        {"site":"肝脏","say":"肝血管瘤","tpl":"肝血管瘤"},
        {"site":"肝脏","say":"肝内胆管结石","tpl":"肝内胆管结石"},
        {"site":"肝脏","say":"肝硬化","tpl":"肝硬化"},
        {"site":"肝脏","say":"肝大","tpl":"肝大"},
        {"site":"胆囊","say":"胆囊大小正常，壁光滑","tpl":"正常胆囊"},
        {"site":"胆囊","say":"胆囊多发结石","tpl":"胆囊多发结石"},
        {"site":"胆囊","say":"胆囊息肉","tpl":"胆囊息肉样病变"},
        {"site":"胆囊","say":"胆囊胆固醇结晶","tpl":"胆囊胆固醇结晶"},
        {"site":"胆囊","say":"胆囊壁毛糙","tpl":"胆囊毛糙"},
        {"site":"胆囊","say":"胆囊壁增厚","tpl":"胆囊壁增厚"},
        {"site":"心脏","say":"各房室内径正常，各瓣膜清晰","tpl":"心内结构未见明显异常"},
        {"site":"心脏","say":"二尖瓣口轻度返流","tpl":"二尖瓣口轻度返流"},
        {"site":"心脏","say":"三尖瓣口轻度返流","tpl":"三尖瓣口轻度返流"},
        {"site":"心脏","say":"主动脉瓣口轻度返流","tpl":"主动脉瓣口轻度返流"},
        {"site":"心脏","say":"主动脉瓣退行性变","tpl":"主动脉瓣退行性变"},
        {"site":"心脏","say":"心包腔积液","tpl":"心包腔积液"},
        {"site":"心脏","say":"左室假腱索","tpl":"左室假腱索"},
        {"site":"心脏","say":"心动过缓","tpl":"心动过缓"},
        {"site":"心脏","say":"室间隔缺损","tpl":"室间隔缺损"},
        {"site":"甲状腺","say":"甲状腺形态规则，大小正常","tpl":"甲状腺(正常)"},
        {"site":"甲状腺","say":"甲状腺回声不均匀","tpl":"甲状腺回声不均匀"},
        {"site":"甲状腺","say":"甲状腺实质弥漫性病变","tpl":"甲状腺实质弥漫性病变"},
        {"site":"甲状腺","say":"甲状腺有结节","tpl":"甲状腺单发结节"},
        {"site":"甲状腺","say":"甲状腺多发结节","tpl":"甲状腺双侧叶多发结节"},
        {"site":"甲状腺","say":"甲状腺无回声结节","tpl":"甲状腺无回声结节（单发）"},
        {"site":"甲状腺","say":"甲状腺全切术后","tpl":"甲状腺全切术后"},
        {"site":"甲状腺","say":"桥本氏甲状腺炎","tpl":"桥本氏甲状腺炎"},
        {"site":"甲状腺","say":"双侧颈部淋巴结未见肿大","tpl":"颈部淋巴结正常"},
        {"site":"乳腺","say":"双乳组织增厚，豹纹征","tpl":"双乳小叶增生 1类"},
        {"site":"乳腺","say":"双侧乳腺增生","tpl":"双侧乳腺增生"},
        {"site":"乳腺","say":"乳腺有囊肿","tpl":"乳腺囊肿（单发）"},
        {"site":"乳腺","say":"乳腺有结节","tpl":"乳腺结节单发"},
        {"site":"乳腺","say":"乳腺导管扩张","tpl":"乳腺导管扩张"},
        {"site":"乳腺","say":"腋窝淋巴结正常","tpl":"腋窝淋巴结正常"},
        {"site":"乳腺","say":"哺乳期乳腺","tpl":"哺乳期乳腺"},
        {"site":"乳腺","say":"乳腺纤维瘤","tpl":"乳腺纤维瘤"},
        {"site":"前列腺","say":"前列腺大小正常","tpl":"正常男性膀胱前列腺"},
        {"site":"前列腺","say":"前列腺稍大","tpl":"前列腺稍大"},
        {"site":"前列腺","say":"前列腺增生","tpl":"前列腺增生"},
        {"site":"前列腺","say":"前列腺有钙化灶","tpl":"前列腺钙化灶"},
        {"site":"前列腺","say":"前列腺有囊肿","tpl":"前列腺囊肿"},
        {"site":"前列腺","say":"前列腺增大","tpl":"前列腺增大"},
        {"site":"双肾","say":"双肾形态规则，大小正常","tpl":"正常双侧肾上腺"},
        {"site":"双肾","say":"肾有结石","tpl":"肾结石（单发）"},
        {"site":"双肾","say":"双肾多发结石","tpl":"双肾多发结石"},
        {"site":"双肾","say":"肾有囊肿","tpl":"肾囊肿（单发）"},
        {"site":"双肾","say":"肾积水","tpl":"肾积水"},
        {"site":"双肾","say":"肾错构瘤","tpl":"肾错构瘤"},
        {"site":"子宫附件","say":"子宫前位，大小正常","tpl":"正常子宫"},
        {"site":"子宫附件","say":"子宫有肌瘤","tpl":"子宫肌瘤"},
        {"site":"子宫附件","say":"卵巢有囊肿","tpl":"卵巢囊肿"},
        {"site":"子宫附件","say":"宫颈多发囊肿","tpl":"宫颈多发囊肿"},
        {"site":"子宫附件","say":"盆腔积液","tpl":"盆腔积液"},
        {"site":"子宫附件","say":"绝经后子宫","tpl":"绝经后子宫声像"},
        {"site":"颈动脉","say":"颈动脉内膜光滑","tpl":"正常颈动脉"},
        {"site":"颈动脉","say":"颈动脉内膜增厚","tpl":"双侧颈动脉内中膜增厚"},
        {"site":"颈动脉","say":"内膜毛糙","tpl":"内膜稍毛糙"},
        {"site":"颈动脉","say":"颈动脉有斑块","tpl":"颈动脉（钙化斑）"},
        {"site":"颈动脉","say":"纤维斑块","tpl":"（纤维成分为主）斑块"},
        {"site":"脾","say":"脾厚正常","tpl":"副脾"},
        {"site":"脾","say":"脾内钙化灶","tpl":"脾内钙化灶"},
        {"site":"脾","say":"脾囊肿","tpl":"脾囊肿"},
        {"site":"脾","say":"脾大","tpl":"脾大"},
        {"site":"睾丸","say":"睾丸、附睾未见异常","tpl":"睾丸 附睾"},
        {"site":"睾丸","say":"附睾头囊肿","tpl":"附睾头囊肿"},
        {"site":"睾丸","say":"精索静脉曲张","tpl":"精索静脉曲张"},
    ]
    return data
