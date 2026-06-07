"""胎儿超声固定模板 — 3色标记：黑=模板主体，橙=AI提取需核验，蓝=未填需手动"""
import re
from cn_num import cn_to_arabic


FETAL_SEE="""<div class="rpt-sec"><b class="rpt-label">【胎儿超声测值】</b>
双顶径{_bpd}cm，相当于{_bpd_ga}Wd；头围{_hc}cm，腹围{_ac}cm，股骨长{_fl}cm，相当于{_fl_ga}Wd；肱骨长{_hl}cm，相当于{_hl_ga}Wd；小脑横径{_tcd}cm；胎儿体重{_efw}±克。</div>
<div class="rpt-sec">羊水最大平段{_afv}cm，羊水指数{_afi}cm。右下{_af_q1}cm、右上{_af_q2}cm、左上{_af_q3}cm、左下{_af_q4}cm。</div>
<div class="rpt-sec">脐带血流：Vmax{_ua_vmax}cm/s，RI{_ua_ri}，PI{_ua_pi}，S/D{_ua_sd}。胎儿心率{_hr}次/分，心律齐。</div>
<div class="rpt-sec"><b class="rpt-label">【胎儿超声结构描述】</b>
胎位：[{_pos_head}头|{_pos_breach}臀|{_pos_trans}横]位。<br>
<b>胎儿头部：</b>[{_skull_normal}颅骨呈圆形光环|{_skull_abnormal}颅骨形态不规则]，[{_midline_center}脑中线居中|{_midline_offset}脑中线偏移]，侧脑室[{_lv_normal}未见增宽，宽约|{_lv_wide}增宽，宽约]{_lvw}cm。两侧丘脑可见。透明隔腔可见，[{_cereb_normal}小脑半球形态无明显异常|{_cereb_abnormal}小脑半球形态异常]，[{_vermis_visible}小脑蚓部可见|{_vermis_hidden}小脑蚓部显示不清]，后颅窝池[{_cmf_normal}未见增宽，宽约|{_cmf_wide}增宽，宽约]{_cm}cm。<br>
<b>胎儿颈部：</b>胎儿颈部[{_neck_none}未见脐带缠绕压迹|{_neck_u}皮肤可见"U"形压迹|{_neck_w}皮肤可见"W"形压迹]。<br>
<b>胎儿颜面：</b>双侧眼球可显示，胎儿上唇皮肤回声未见明显连续性中断，双侧口角线显示不清。胎儿鼻骨约{_nasal_bone}cm。[{_ear_both}胎儿双/左/右侧耳廓部分可见|{_ear_left}胎儿左/右侧耳廓部分可见，由于胎儿体位受限，左/右侧耳廓显示不清|{_ear_none}由于胎儿体位受限，左/右/双侧耳廓显示不清]。<br>
<b>胎儿脊柱：</b>脊柱纵切显示连续且排列整齐，呈"串珠"状，横切时呈"品"字结构。<br>
<b>胎儿心脏：</b>[{_4ch_clear}四腔心切面可清楚显示|{_4ch_blur}四腔心切面显示不清]，左、右房室大小基本对称，左、右心房与左、右心室连接一致，[{_cross_present}心脏中央"十"字交叉存在|{_cross_absent}心脏中央"十"字交叉消失]，二尖瓣及三尖瓣清楚，启闭运动两侧均可见，左右心室流出道切面显示清楚，[{_va_consistent}心室与大动脉连接关系一致|{_va_inconsistent}心室与大动脉连接关系不一致]。<br>
<b>胎儿腹部内脏：</b>肝、胃、双肾、膀胱、胆囊可见。[{_renal_normal}胎儿双侧肾盂未见明显分离|{_renal_sep}胎儿双侧肾盂分离]。<br>
<b>胎儿四肢：</b>双侧上臂及其内的肱骨可见，双侧前臂及其内的尺、桡骨可见，双手呈握拳状，指骨显示不清。双侧大腿及其内的股骨可见，双侧小腿及其内的胫、腓骨可见，双足可见，趾骨显示不清。足长约{_foot_len}cm。<br>
<b>胎儿脐带：</b>可见脐带血管由一条脐静脉两条脐动脉组成。<br>
<b>胎盘：</b>附着在子宫[{_pl_ant}前|{_pl_post}后|{_pl_left}左|{_pl_right}右]壁，胎盘{_pl_grade}级，厚约{_pl_thick}cm。<br>
<b>胎儿生物物理相观察：</b>[{_biophys_normal}呼吸运动、胎动正常|{_biophys_reduced}呼吸运动减弱|{_biophys_absent}未见呼吸运动及胎动]，曲伸运动可见。</div>
<div class="rpt-sec"><b>母体：</b>经腹部超声观察，母体宫颈管长约{_cervix_len}cm，[{_cx_normal}未见扩张声像|{_cx_dilated}宫颈管扩张]。子宫动脉搏动指数：左侧{_ut_pi_l}，右侧{_ut_pi_r}。</div>"""
M_FIELDS = {
"_bpd":"双顶径","_bpd_ga":"孕周","_hc":"头围","_ac":"腹围","_fl":"股骨长","_fl_ga":"孕周",
"_hl":"肱骨长","_hl_ga":"孕周","_tcd":"小脑横径","_efw":"估测体重",
"_afv":"羊水平段","_afi":"羊水指数","_af_q1":"右下","_af_q2":"右上","_af_q3":"左上","_af_q4":"左下","_afi2":"羊水指数",
"_ua_vmax":"Vmax","_ua_ri":"RI","_ua_pi":"PI","_ua_sd":"S/D","_hr":"胎心率",
"_lvw":"侧脑室宽","_cm":"后颅窝池","_nasal_bone":"鼻骨长","_foot_len":"足长",
"_cervix_len":"宫颈管长","_ut_pi_l":"左侧PI","_ut_pi_r":"右侧PI","_pl_thick":"胎盘厚","_pl_grade":"胎盘等级",
}

MEASUREMENTS=[
	(r"双顶径(?:大约|约|大概)?\s*[：:=]?\s*(\d+(?:\.\d+)?)","_bpd"),(r"BPD\s*[：:=约]?\s*(\d+(?:\.\d+)?)","_bpd"),
	(r"头顶径\s*[：:=]?\s*(\d+(?:\.\d+)?)","_bpd"),
	(r"头围\s*[：:=]?\s*(\d+(?:\.\d+)?)","_hc"),(r"HC\s*[：:=]?\s*(\d+(?:\.\d+)?)","_hc"),
	(r"腹围\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ac"),(r"AC\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ac"),
	(r"股骨长\s*[：:=]?\s*(\d+(?:\.\d+)?)","_fl"),(r"FL\s*[：:=]?\s*(\d+(?:\.\d+)?)","_fl"),
	(r"肱骨长\s*[：:=]?\s*(\d+(?:\.\d+)?)","_hl"),(r"HL\s*[：:=]?\s*(\d+(?:\.\d+)?)","_hl"),
	(r"(?:胎心|胎心率|心率|心跳|FHR?)\s*[：:=]?\s*(\d{2,3})","_hr"),
	(r"(\d{2,3})\s*(?:次|ci)?\s*[/／]?\s*分","_hr"),
	(r"羊水指数\s*[：:=]?\s*(\d+(?:\.\d+)?)","_afi"),(r"AFI\s*[：:=]?\s*(\d+(?:\.\d+)?)","_afi"),
	(r"羊水(?:最大)?(?:平段|深度|暗区)\s*[：:=]?\s*(\d+(?:\.\d+)?)","_afv"),
	(r"(?:胎儿|估测)?体重\s*[：:=]?\s*(\d+)\s*(?:±\s*\d+)?\s*(?:克|g)?","_efw"),(r"EFW\s*[：:=]?\s*(\d+)","_efw"),
	(r"(?:脐动?脉?|脐带)?\s*(?:S\s*/\s*D|SD)[：:=]?\s*(\d+(?:\.\d+)?)","_ua_sd"),
	(r"(?:脐动?脉?|脐带)?\s*RI\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ua_ri"),
	(r"(?:脐动?脉?|脐带)?\s*PI\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ua_pi"),
	(r"(?:脐动?脉?|脐带)?\s*Vmax\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ua_vmax"),
	(r"小脑横径\s*[：:=]?\s*(\d+(?:\.\d+)?)","_tcd"),(r"鼻骨(?:约)?\s*[：:=]?\s*(\d+(?:\.\d+)?)","_nasal_bone"),
	(r"足长\s*[：:=]?\s*(\d+(?:\.\d+)?)","_foot_len"),(r"足长(?:约)?\s*(\d+(?:\.\d+)?)(?:\s*cm|\s*厘米)?","_foot_len"),(r"宫颈(?:管)?长(?:约)?\s*[：:=]?\s*(\d+(?:\.\d+)?)","_cervix_len"),
	(r"胎盘[^，。]*?厚(?:度|约)?\s*(\d+(?:\.\d+)?)","_pl_thick"),(r"胎盘\s*([0-3I]{1,3})\s*级","_pl_grade"),
	(r"侧脑室(?:宽)?\s*[：:=]?\s*(\d+(?:\.\d+)?)","_lvw"),(r"后颅窝池\s*[：:=]?\s*(\d+(?:\.\d+)?)","_cm"),
	(r"(?:左侧|左)?\s*子宫动脉(?:搏动指数)?\s*(?:左侧|左)\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ut_pi_l"),(r"(?:右侧|右)?\s*子宫动脉(?:搏动指数)?\s*[^。]*?右侧\s*[：:=]?\s*(\d+(?:\.\d+)?)","_ut_pi_r"),
	(r"右下\s*[：:=]?\s*(\d+(?:\.\d+)?)","_af_q1"),(r"右上\s*[：:=]?\s*(\d+(?:\.\d+)?)","_af_q2"),(r"左上\s*[：:=]?\s*(\d+(?:\.\d+)?)","_af_q3"),(r"左下\s*[：:=]?\s*(\d+(?:\.\d+)?)","_af_q4"),
	# 孕周识别

	(r"(?:中?孕|四维|排畸|彩超|停经|晚期|中期|早期).*?(\d{2})\s*[-~～到至为]\s*(\d{2})(?:\s*[周Ww])?","_ga_range"),
	(r"(?:中?孕|四维|排畸|彩超|停经|晚期|中期|早期)\s*(\d{2})\s*[周Ww](?:\s*(?:天|日))?","_ga_single"),
	(r"(?:约|大概|左右|相当于?|超声孕?)\s*(\d{2})\s*[周Ww]","_ga_approx"),
	(r"(?:^|[^0-9,.])(\d{2})\s*[周Ww](?:\s*(?:天|日))?","_ga_num"),
	(r"(\d+)\s*点\s*(\d+)\s*(?:cm|厘米|mm|毫米)?","_decimal"),
	# 省略型: "22到26" "22-26" 无关键字 (loose fallback)
	(r"(?:孕周|大小|胎儿|宝宝|四维|排畸).*?(\d{2})\s*[-~～到至为]\s*(\d{2})","_ga_range"),
]
OPTIONS=[(r"头位","_pos_head"),(r"臀位","_pos_breach"),(r"横位","_pos_trans"),
(r"前壁","_pl_ant"),(r"后壁","_pl_post"),(r"左壁","_pl_left"),(r"右壁","_pl_right"),(r"胎盘.*前壁","_pl_ant"),(r"胎盘.*后壁","_pl_post"),(r"胎盘.*左壁","_pl_left"),(r"胎盘.*右壁","_pl_right"),
(r"(?:未见|没有|无)(?:脐带)?缠绕","_neck_none"),(r"[UＵ]型","_neck_u"),(r"[WＷ]型","_neck_w"),
(r"双.*耳廓.*可见","_ear_both"),(r"左.*耳廓.*可见","_ear_left"),(r"耳廓.*不清","_ear_none"),(r"耳廓.*显示不清","_ear_none"),
]
OPTIONS_ANTONYM=[(r"不规则|形态不规则|颅骨不规则","_skull_abnormal"),(r"颅骨呈圆形|形态规则|颅骨规则","_skull_normal"),
	(r"侧脑室增宽|脑室增宽|侧脑室扩张","_lv_wide"),(r"侧脑室正常|脑室未见增宽|脑室正常","_lv_normal"),
	(r"小脑半球.*异常|小脑异常|小脑畸形","_cereb_abnormal"),(r"小脑半球.*正常|小脑正常|小脑无异常","_cereb_normal"),
	(r"小脑蚓部.*不清|蚓部不清|小脑蚓部缺如","_vermis_hidden"),(r"小脑蚓部可见|蚓部可见","_vermis_visible"),
	(r"后颅窝池.*宽|后颅窝增宽|颅后窝增宽","_cmf_wide"),(r"后颅窝.*正常|后颅窝未见增宽","_cmf_normal"),
	(r"四腔心.*不清|四腔心显示欠佳|四腔心未显示","_4ch_blur"),
	(r"十字交叉消失|十字交叉未见|十字交叉缺如","_cross_absent"),
	(r"大动脉连接.*不一致|心室大动脉.*不一致","_va_inconsistent"),
	(r"肾盂分离|肾盂扩张","_renal_sep"),(r"肾盂未见分离|肾盂无分离|肾盂正常","_renal_normal"),
	(r"胎动.*未见|未见胎动|胎动消失","_biophys_absent"),(r"呼吸.*减弱|胎动.*减弱|胎动减少","_biophys_reduced"),
	(r"宫颈.*扩张|宫颈管扩张|宫颈口扩张","_cx_dilated"),
]
OPTIONS += OPTIONS_ANTONYM

OPT_RESET={"_pos_head":("_pos_head","_pos_breach","_pos_trans"),"_pos_breach":("_pos_head","_pos_breach","_pos_trans"),"_pos_trans":("_pos_head","_pos_breach","_pos_trans"),
"_neck_none":("_neck_none","_neck_u","_neck_w"),"_neck_u":("_neck_none","_neck_u","_neck_w"),"_neck_w":("_neck_none","_neck_u","_neck_w"),
"_pl_ant":("_pl_ant","_pl_post","_pl_left","_pl_right"),"_pl_post":("_pl_ant","_pl_post","_pl_left","_pl_right"),"_pl_left":("_pl_ant","_pl_post","_pl_left","_pl_right"),"_pl_right":("_pl_ant","_pl_post","_pl_left","_pl_right"),
"_ear_both":("_ear_both","_ear_left","_ear_none"),"_ear_left":("_ear_both","_ear_left","_ear_none"),"_ear_none":("_ear_both","_ear_left","_ear_none"),
}
OPTION_KEYS = set(OPT_RESET.keys()) | {key for _,key in OPTIONS_ANTONYM}

def fill_fetal_template(raw_text:str)->dict:
    raw_text = cn_to_arabic(raw_text)
    raw_text = re.sub(r'(\d+(?:\.\d+)?)\s*公斤', lambda m: str(int(float(m.group(1))*1000))+'克', raw_text)
    raw_text = re.sub(r'(\d+(?:\.\d+)?)\s*(?:kg|千克)', lambda m: str(int(float(m.group(1))*1000))+'克', raw_text, flags=re.IGNORECASE)
    raw_text = raw_text.replace('平面','平段')
    vals={}; opts={"_neck_none":"selected"}; ga_val=None

    # 优先从检查上下文(四维/中孕/早孕)提取明确的孕周
    import re as _re2
    ga_explicit_patterns = [
        r"[四4][维維]\s*(\d{2})\s*[-~～到至为]\s*(\d{2})",
        r"中[晚]?孕\s*\D{0,4}(\d{2})\s*[-~～到至为]\s*(\d{2})",
        r"早孕\s*\D{0,4}(\d{2})\s*[-~～到至为]\s*(\d{2})",
    ]
    ga_explicit_val = None
    for p in ga_explicit_patterns:
        m = _re2.search(p, raw_text)
        if m:
            g1, g2 = int(m.group(1)), int(m.group(2))
            if 14 <= g1 <= 42 and 14 <= g2 <= 42:
                ga_explicit_val = f"{g1}-{g2}"
                break

    for pat,key in MEASUREMENTS:
        m=re.search(pat,raw_text)
        if not m: continue
        if key in ("_ga_range","_ga_single","_ga_approx","_ga_num"):
            # 如果匹配到的位置在"建议"之后，跳过(避免把建议中的孕周当测量值)
            rec_pos = raw_text.find("建议")
            if rec_pos >= 0 and m.start() >= rec_pos:
                continue
            # 优先用显式GA，跳过模糊匹配
            if ga_explicit_val:
                continue
            g1=m.group(1); g2=m.group(2) if m.lastindex and m.lastindex>=2 else None
            if g2: ga_val=f"{g1}-{g2}"
            elif not ga_val: ga_val=f"{g1}"
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

    # === 逐测量项提取"相当于 XX 周" ===
    # 策略：对每个测量项独立提取它后面最近的"相当于"值
    # 避免全局ga_val被最后一个"相当于"覆盖，导致前面的项丢失
    GA_PATTERNS = [
        (r"双顶径.*?相当于?\s*(\d{2})\s*[-~～到至为]\s*(\d{2})", "_bpd_ga_range"),
        (r"双顶径.*?相当于?\s*(\d{2})\s*[周Ww]", "_bpd_ga"),
        (r"BPD.*?相当于?\s*(\d{2})\s*[-~～到至为]\s*(\d{2})", "_bpd_ga_range"),
        (r"BPD.*?相当于?\s*(\d{2})\s*[周Ww]", "_bpd_ga"),
        (r"股骨长.*?相当于?\s*(\d{2})\s*[-~～到至为]\s*(\d{2})", "_fl_ga_range"),
        (r"股骨长.*?相当于?\s*(\d{2})\s*[周Ww]?", "_fl_ga"),
        (r"FL.*?相当于?\s*(\d{2})\s*[-~～到至为]\s*(\d{2})", "_fl_ga_range"),
        (r"FL.*?相当于?\s*(\d{2})\s*[周Ww]?", "_fl_ga"),
        (r"肱骨长.*?相当于?\s*(\d{2})\s*[-~～到至为]\s*(\d{2})", "_hl_ga_range"),
        (r"肱骨长.*?相当于?\s*(\d{2})\s*[周Ww]?", "_hl_ga"),
        (r"HL.*?相当于?\s*(\d{2})\s*[-~～到至为]\s*(\d{2})", "_hl_ga_range"),
        (r"HL.*?相当于?\s*(\d{2})\s*[周Ww]?", "_hl_ga"),
        (r"头围.*?相当于?\s*(\d{2})\s*[-~～到至为]\s*(\d{2})", "_hc_ga_range"),
        (r"头围.*?相当于?\s*(\d{2})\s*[周Ww]?", "_hc_ga"),
        (r"腹围.*?相当于?\s*(\d{2})\s*[-~～到至为]\s*(\d{2})", "_ac_ga_range"),
        (r"腹围.*?相当于?\s*(\d{2})\s*[周Ww]?", "_ac_ga"),
    ]

    for pat, key in GA_PATTERNS:
        m = re.search(pat, raw_text)
        if not m:
            continue
        if key.endswith("_range"):
            base_key = key[:-len("_range")]
            vals[base_key] = f"{m.group(1)}-{m.group(2)}"
        else:
            if key not in vals:  # 优先保留 range 结果
                vals[key] = m.group(1)

    # 全局 GA 兜底（优先用显式提取的ga_explicit_val，覆盖模糊匹配的ga_val）
    if ga_explicit_val:
        ga_val = ga_explicit_val
    if ga_val:
        if "_bpd_ga" not in vals:
            vals["_bpd_ga"] = ga_val
        if "_fl_ga" not in vals:
            vals["_fl_ga"] = ga_val
        if "_hl_ga" not in vals:
            vals["_hl_ga"] = ga_val

    for pat,key in OPTIONS:
        if re.search(pat,raw_text):
            for rk in OPT_RESET.get(key,(key,)): opts[rk]=False
            opts[key]=True

    # GA 缺失时按公式推算（兜底）
    if "_bpd_ga" not in vals and "_bpd" in vals:
        vals["_bpd_ga"] = str(round(float(vals["_bpd"]) * 4 + 2))
    if "_fl_ga" not in vals and "_fl" in vals:
        vals["_fl_ga"] = str(round(float(vals["_fl"]) * 6.5 + 3))
    if "_hl_ga" not in vals and "_hl" in vals:
        vals["_hl_ga"] = str(round(float(vals["_hl"]) * 6.5 + 3))
    if "_hc_ga" not in vals and "_hc" in vals:
        vals["_hc_ga"] = str(round(float(vals["_hc"]) * 4 + 2))
    if "_ac_ga" not in vals and "_ac" in vals:
        vals["_ac_ga"] = str(round(float(vals["_ac"]) * 4 + 2))

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

    # 从原文提取建议文本 (匹配"建议："后面的内容)
    import re as _re2
    rec_text = "建议定期产检。"
    rec_matches = _re2.findall(r'建议[：:]\s*(.+?)(?:[。；;]|$)', raw_text)
    if rec_matches:
        rec_text = "建议" + "；".join(rec_matches) + "。"

    # 从原文提取孕周信息, 避免把"30-34周行检查"误解析为孕周
    # 方法: 优先使用"四维"、"中孕"、"早孕"、"晚孕"明确标记的孕周
    ga_val_explicit = None
    ga_explicit_patterns = [
        r"四维\s*(\d{2})\s*[-~～到至为]\s*(\d{2})",
        r"中[晚]?孕\s*\D{0,4}(\d{2})\s*[-~～到至为]\s*(\d{2})",
        r"早孕\s*\D{0,4}(\d{2})\s*[-~～到至为]\s*(\d{2})",
    ]
    for pat in ga_explicit_patterns:
        m = _re2.search(pat, raw_text)
        if m:
            g1, g2 = m.group(1), m.group(2)
            # 只取合理的孕周范围(14-42周)
            if 14 <= int(g1) <= 42 and 14 <= int(g2) <= 42:
                ga_val_explicit = f"{g1}-{g2}"
                break

    # reset GA to explicit value from exam context, not from recommendation text
    if ga_val_explicit:
        ga_val = ga_val_explicit

    return {"patient_info":{"name":None,"gender":None,"age":None,"exam_id":None},
     "exam_info":{"modality":"产科超声","device":None,"exam_date":None},
     "study_see":'<div class="rpt-html">'+see+'</div>',
     "study_hint":[{"rank":1,"diagnosis":hint,"icd10":""}],
     "recommendation":rec_text,
     "_template_matched":"胎儿超声标准模板","_method":"fetal_template"}
