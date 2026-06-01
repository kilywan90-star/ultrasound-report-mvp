"""胎儿超声固定模板 — 3色标记：黑=模板主体，橙=AI提取需核验，蓝=未填需手动"""
import re

FETAL_SEE="""<div class="rpt-sec"><b class="rpt-label">【胎儿超声测值】</b>
双顶径{_bpd}cm，相当于{_bpd_ga}Wd；头围{_hc}cm，腹围{_ac}cm，股骨长{_fl}cm，相当于{_fl_ga}Wd；肱骨长{_hl}cm，相当于{_hl_ga}Wd；小脑横径{_tcd}cm；胎儿体重{_efw}±克。</div>
<div class="rpt-sec">羊水最大平段{_afv}cm，羊水指数{_afi}cm。右下{_af_q1}cm、右上{_af_q2}cm、左上{_af_q3}cm、左下{_af_q4}cm。</div>
<div class="rpt-sec">脐带血流：Vmax{_ua_vmax}cm/s，RI{_ua_ri}，PI{_ua_pi}，S/D{_ua_sd}。胎儿心率{_hr}次/分，心律齐。</div>
<div class="rpt-sec"><b class="rpt-label">【胎儿超声结构描述】</b>
胎位：[{_pos_head}头|{_pos_breach}臀|{_pos_trans}横]位。<br>
<b>胎儿头部：</b>颅骨呈圆形光环，脑中线居中，侧脑室宽约{_lvw}cm。两侧丘脑可见。透明隔腔可见，小脑半球形态无明显异常，小脑蚓部可见，后颅窝池宽约{_cm}cm。<br>
<b>胎儿颈部：</b>胎儿颈部[{_neck_none}未见脐带缠绕压迹|{_neck_u}皮肤可见"U"形压迹|{_neck_w}皮肤可见"W"形压迹]。<br>
<b>胎儿颜面：</b>双侧眼球可显示，胎儿上唇皮肤回声未见明显连续性中断。胎儿鼻骨约{_nasal_bone}cm。[{_ear_both}胎儿双/左/右侧耳廓部分可见|{_ear_left}胎儿左/右侧耳廓部分可见|{_ear_none}由于胎儿体位受限，耳廓显示不清]。<br>
<b>胎儿脊柱：</b>脊柱纵切显示连续且排列整齐，呈"串珠"状，横切时呈"品"字结构。<br>
<b>胎儿心脏：</b>四腔心切面可清楚显示，左、右房室大小基本对称，二尖瓣及三尖瓣清楚，启闭运动两侧均可见，左右心室流出道切面显示清楚。<br>
<b>胎儿腹部内脏：</b>肝、胃、双肾、膀胱、胆囊可见。胎儿双侧肾盂未见明显分离。<br>
<b>胎儿四肢：</b>双侧上臂及其内的肱骨可见，双侧前臂及其内的尺、桡骨可见，双手呈握拳状。双侧大腿及其内的股骨可见，双侧小腿及其内的胫、腓骨可见。足长约{_foot_len}cm。<br>
<b>胎儿脐带：</b>可见脐带血管由一条脐静脉两条脐动脉组成。<br>
<b>胎盘：</b>附着在子宫[{_pl_ant}前|{_pl_post}后|{_pl_left}左|{_pl_right}右]壁，胎盘{_pl_grade}级，厚约{_pl_thick}cm。<br>
<b>胎儿生物物理相观察：</b>呼吸运动、胎动正常，曲伸运动可见。</div>
<div class="rpt-sec"><b>母体：</b>宫颈管长约{_cervix_len}cm，未见扩张声像。子宫动脉搏动指数：左侧{_ut_pi_l}，右侧{_ut_pi_r}。</div>"""

# 仅数值型字段（不包含选项）
M_FIELDS = {
"_bpd":"双顶径","_bpd_ga":"孕周","_hc":"头围","_ac":"腹围","_fl":"股骨长","_fl_ga":"孕周",
"_hl":"肱骨长","_hl_ga":"孕周","_tcd":"小脑横径","_efw":"估测体重",
"_afv":"羊水平段","_afi":"羊水指数","_af_q1":"右下","_af_q2":"右上","_af_q3":"左上","_af_q4":"左下","_afi2":"羊水指数",
"_ua_vmax":"Vmax","_ua_ri":"RI","_ua_pi":"PI","_ua_sd":"S/D","_hr":"胎心率",
"_lvw":"侧脑室宽","_cm":"后颅窝池","_nasal_bone":"鼻骨长","_foot_len":"足长",
"_cervix_len":"宫颈管长","_ut_pi_l":"左侧PI","_ut_pi_r":"右侧PI","_pl_thick":"胎盘厚","_pl_grade":"胎盘等级",
}

MEASUREMENTS=[
(r"双顶径\s*[：:=]?\s*(\d+(?:\.\d+)?)","_bpd"),(r"BPD\s*[：:=]?\s*(\d+(?:\.\d+)?)","_bpd"),
(r"头顶径\s*[：:=]?\s*(\d+(?:\.\d+)?)","_bpd"),
(r"头围\s*[：:=]?\s*(\d+(?:\.\d+)?)","_hc"),(r"HC\s*[：:=]?\s*(\d+(?:\.\d+)?)","_hc"),
(r"腹围\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ac"),(r"AC\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ac"),
(r"股骨长\s*[：:=]?\s*(\d+(?:\.\d+)?)","_fl"),(r"FL\s*[：:=]?\s*(\d+(?:\.\d+)?)","_fl"),
(r"肱骨长\s*[：:=]?\s*(\d+(?:\.\d+)?)","_hl"),(r"HL\s*[：:=]?\s*(\d+(?:\.\d+)?)","_hl"),
(r"(?:胎心|胎心率|心率|心跳|FHR?)\s*[：:=]?\s*(\d{2,3})","_hr"),
(r"羊水指数\s*[：:=]?\s*(\d+(?:\.\d+)?)","_afi"),(r"AFI\s*[：:=]?\s*(\d+(?:\.\d+)?)","_afi"),
(r"羊水(?:最大)?(?:平段|深度|暗区)\s*[：:=]?\s*(\d+(?:\.\d+)?)","_afv"),
(r"(?:胎儿|估测)?体重\s*[：:=]?\s*(\d+)\s*(?:±\s*\d+)?\s*(?:克|g)?","_efw"),(r"EFW\s*[：:=]?\s*(\d+)","_efw"),
(r"(?:脐动?脉?|脐带)?\s*(?:S\s*/\s*D|SD)[：:=]?\s*(\d+(?:\.\d+)?)","_ua_sd"),
(r"(?:脐动?脉?|脐带)?\s*RI\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ua_ri"),
(r"(?:脐动?脉?|脐带)?\s*PI\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ua_pi"),
(r"(?:脐动?脉?|脐带)?\s*Vmax\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ua_vmax"),
(r"小脑横径\s*[：:=]?\s*(\d+(?:\.\d+)?)","_tcd"),(r"鼻骨(?:约)?\s*[：:=]?\s*(\d+(?:\.\d+)?)","_nasal_bone"),
(r"足长\s*[：:=]?\s*(\d+(?:\.\d+)?)","_foot_len"),(r"宫颈(?:管)?长(?:约)?\s*[：:=]?\s*(\d+(?:\.\d+)?)","_cervix_len"),
(r"胎盘厚(?:度)?\s*[：:=]?\s*(\d+(?:\.\d+)?)","_pl_thick"),(r"胎盘\s*([0-3I]{1,3})\s*级","_pl_grade"),
(r"侧脑室(?:宽)?\s*[：:=]?\s*(\d+(?:\.\d+)?)","_lvw"),(r"后颅窝池\s*[：:=]?\s*(\d+(?:\.\d+)?)","_cm"),
(r"左侧子宫动脉\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ut_pi_l"),(r"右侧子宫动脉\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ut_pi_r"),
# 孕周识别
(r"(?:中?孕|四维|排畸|彩超|停经|晚期|中期|早期)\s*(\d{2})\s*[-~～到至]\s*(\d{2})(?:\s*[周W])?","_ga_range"),
(r"(?:中?孕|四维|排畸|彩超|停经|晚期|中期|早期)\s*(\d{2})\s*[周W](?:\s*(?:天|日))?","_ga_single"),
(r"(?:约|大概|左右|相当于?|超声孕?)\s*(\d{2})\s*[周W]","_ga_approx"),
(r"(?:^|[^0-9,.])(\d{2})\s*[周W](?:\s*(?:天|日))?","_ga_num"),
(r"(\d+)\s*点\s*(\d+)\s*(?:cm|厘米|mm|毫米)?","_decimal"),
]

OPTIONS=[(r"头位","_pos_head"),(r"臀位","_pos_breach"),(r"横位","_pos_trans"),
(r"前壁","_pl_ant"),(r"后壁","_pl_post"),(r"左壁","_pl_left"),(r"右壁","_pl_right"),(r"胎盘.*前壁","_pl_ant"),(r"胎盘.*后壁","_pl_post"),(r"胎盘.*左壁","_pl_left"),(r"胎盘.*右壁","_pl_right"),
(r"(?:未见|没有|无)(?:脐带)?缠绕","_neck_none"),(r"[UＵ]型","_neck_u"),(r"[WＷ]型","_neck_w"),
(r"双.*耳廓.*可见","_ear_both"),(r"左.*耳廓.*可见","_ear_left"),(r"耳廓.*不清","_ear_none"),(r"耳廓.*显示不清","_ear_none"),
]

OPT_RESET={"_pos_head":("_pos_head","_pos_breach","_pos_trans"),"_pos_breach":("_pos_head","_pos_breach","_pos_trans"),"_pos_trans":("_pos_head","_pos_breach","_pos_trans"),
"_neck_none":("_neck_none","_neck_u","_neck_w"),"_neck_u":("_neck_none","_neck_u","_neck_w"),"_neck_w":("_neck_none","_neck_u","_neck_w"),
"_pl_ant":("_pl_ant","_pl_post","_pl_left","_pl_right"),"_pl_post":("_pl_ant","_pl_post","_pl_left","_pl_right"),"_pl_left":("_pl_ant","_pl_post","_pl_left","_pl_right"),"_pl_right":("_pl_ant","_pl_post","_pl_left","_pl_right"),
"_ear_both":("_ear_both","_ear_left","_ear_none"),"_ear_left":("_ear_both","_ear_left","_ear_none"),"_ear_none":("_ear_both","_ear_left","_ear_none"),
}
OPTION_KEYS = set(OPT_RESET.keys())

def fill_fetal_template(raw_text:str)->dict:
    vals={}; opts={"_neck_none":"selected"}; ga_val=None

    for pat,key in MEASUREMENTS:
        m=re.search(pat,raw_text)
        if not m: continue
        if key in ("_ga_range","_ga_single","_ga_approx","_ga_num"):
            # _ga_range 优先：22-26 匹配后不再让后续单独匹配22和26
            g1=m.group(1); g2=m.group(2) if m.lastindex and m.lastindex>=2 else None
            if g2: ga_val=f"{g1}-{g2}W"
            elif not ga_val: ga_val=f"{g1}W"
            continue
        if key=="_decimal":
            vals["_temp_decimal"]=m.group(1)+"."+m.group(2)
            continue
        vals[key]=m.group(1)

    # 小数转最近测量字段
    if "_temp_decimal" in vals:
        d=vals.pop("_temp_decimal")
        for k in ("_bpd","_hc","_ac","_fl","_hl","_afi","_afv","_lvw","_cm"):
            if k not in vals: vals[k]=d; break

    if ga_val:
        vals["_bpd_ga"]=ga_val; vals["_fl_ga"]=ga_val; vals["_hl_ga"]=ga_val

    for pat,key in OPTIONS:
        if re.search(pat,raw_text):
            for rk in OPT_RESET.get(key,(key,)): opts[rk]=False
            opts[key]=True  # 用户说了 → True（绿色），未说但默认的保持"selected"（黑色）

    # BPD/FL fallback if no GA spoken
    if not ga_val:
        if "_bpd" in vals: vals["_bpd_ga"]=str(round(float(vals["_bpd"])*4+2))
        if "_fl" in vals: vals["_fl_ga"]=str(round(float(vals["_fl"])*6.5+3))

    # === 构建HTML ===
    see=FETAL_SEE

    # 第1步: 先处理选项 [ ... | ... ]（在占位符替换前）
    def _clean(m):
        parts=m.group(1).split("|")
        for p in parts:
            for key in OPTION_KEYS:
                val = opts.get(key)
                if val and ("{"+key+"}") in p:
                    cleaned=re.sub(r"\{[^}]+\}","",p).strip()
                    if not cleaned: return ""
                    # 默认选中值用普通文本，语音命中值用绿色标记
                    if val == "selected":
                        return f" {cleaned} "
                    return f' <b class="voice">{cleaned}</b> '
        first=re.sub(r"\{[^}]+\}","",parts[0]).strip() if parts else ""
        return f" {first} "
    see=re.sub(r"\[([^\]]*?)\]",_clean,see)

    # 第2步: 数值型占位符
    for key in sorted(M_FIELDS.keys(), key=len, reverse=True):
        v=vals.get(key,"")
        if v and v!="___":
            see=see.replace("{"+key+"}",f'<b class="voice">{v}</b>')
        else:
            see=see.replace("{"+key+"}",f'<i class="unfill">__</i>')

    # 第3步: 清理残余占位符（不经过前两步的选项键残余）
    for key in OPTION_KEYS:
        see=see.replace("{"+key+"}","")
    see=re.sub(r"\{_[^}]+\}",'<i class="unfill">__</i>',see)
    see=re.sub(r"[ ]{2,}"," ",see).strip()

    pos="头位"
    if opts.get("_pos_breach"):pos="臀位"
    elif opts.get("_pos_trans"):pos="横位"
    hint=f"宫内妊娠，单活胎，{pos}。"
    if ga_val: hint+=f" 超声孕周{ga_val}。"

    return {"patient_info":{"name":None,"gender":None,"age":None,"exam_id":None},
     "exam_info":{"modality":"产科超声","device":None,"exam_date":None},
     "study_see":'<div class="rpt-html">'+see+'</div>',
     "study_hint":[{"rank":1,"diagnosis":hint,"icd10":""}],
     "recommendation":"建议定期产检。",
     "_template_matched":"胎儿超声标准模板","_method":"fetal_template"}
