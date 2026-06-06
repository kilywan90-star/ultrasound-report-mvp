"""自动生成 — abdomen 结构化模板"""
from template_converted import register_templates

_TPL = {
    '正常男性腹部全套（无门静脉）': {
        'html': '<div class="rpt-sec">肝脏形态规则，大小正常，表面光滑，实质回声分布均匀，肝内管系尚清。</div>',
        'fields': {},
    },
    '肝、胆、脾、胰、双肾、输尿管未见明显异常声像。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '正常女性腹部全套（无门静脉）': {
        'html': '<div class="rpt-sec">肝脏形态规则，大小正常，表面光滑， 实质回声分布均匀，肝内管系尚清。</div>',
        'fields': {},
    },
    '胆囊多发结石': {
        'html': '<div class="rpt-sec">胆囊大小形态正常，壁欠光滑，内见多个强回声团，后伴声影，改变体位可移动,较大约 x{_大约_0}mm，胆总管上段内径正常。</div>',
        'fields': {"_大约_0": ",较大约 x"},
    },
    '胆囊充填型结石': {
        'html': '<div class="rpt-sec">胆囊区未探及明显正常胆囊声像，可见一弧形强光带，长{_带长_0}mm，后方伴大片声影，呈“WES”征，胆总管上段内径正常。</div>',
        'fields': {"_带长_0": "形强光带，长"},
    },
    '胆囊多发息肉样病变': {
        'html': '<div class="rpt-sec">胆囊大小形态正常，壁欠光滑，内见多个附壁稍高回声结节，无声影，改变体位不移动，较大约x{_大约_0}mm，胆总管上段内径正常。</div>',
        'fields': {"_大约_0": "动，较大约x"},
    },
    '肝囊肿（单发）': {
        'html': '<div class="rpt-sec">肝内可见无回声区，大小约 x{_size_0}mm，壁薄，后壁回声增强，内透声可。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '肝多发囊肿': {
        'html': '<div class="rpt-sec">肝内可见多个无回声区，壁薄，内透声可，后壁回声增强，其一大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "一大小约 x"},
    },
    '肝内钙化灶': {
        'html': '<div class="rpt-sec">肝内可见一强回声斑，大小约 x{_size_0}mm，后无声影。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '肝多发血管瘤': {
        'html': '<div class="rpt-sec">肝内可见多个稍高/稍低/等回声结节，形态规则，边界尚清，内部回声欠均匀，内呈网格状改变，后方回声无衰减，较大约 x{_大约_0}mm。</div>',
        'fields': {"_大约_0": "，较大约 x"},
    },
    '肝内胆管结石': {
        'html': '<div class="rpt-sec">右肝前叶/右肝后叶，左肝内叶/左肝外叶见沿胆管分布的强光团/带，后伴声影，远端胆管稍扩张，{_扩张_0}mm，范围约 x{_diameter_1}mm。</div>',
        'fields': {"_扩张_0": "胆管稍扩张，", "_diameter_1": "，范围约 x"},
    },
    '肝内胆管多发结石': {
        'html': '<div class="rpt-sec">右肝前叶/右肝后叶，左肝内叶/左肝外叶见多个沿胆管分布的强回声团/带，后伴声影，较大约 x{_大约_0}mm，远端胆管稍扩张，{_扩张_1}mm。</div>',
        'fields': {"_大约_0": "，较大约 x", "_扩张_1": "胆管稍扩张，"},
    },
    '肝硬化': {
        'html': '<div class="rpt-sec">肝脏形态欠规则,体积正常/缩小,肝包膜表面欠光滑/呈锯齿状,实质回声增粗,分布不均匀,管系结构显示不清晰/走形欠/不规则。</div>\n<div class="rpt-sec">CDFI：示肝静脉变细，血流信号减少。</div>',
        'fields': {},
    },
    '多囊肝': {
        'html': '<div class="rpt-sec">肝脏形态欠规则,轮廓增大，表面欠光滑，正常肝实质/部分肝实质回声几乎消失，可见大小不等的无回声区，较大约 x{_大约_0}mm，边界清晰/欠清晰，壁薄，光滑，后方回声增强，囊与囊之间彼此不相连通。</div>',
        'fields': {"_大约_0": "，较大约 x"},
    },
    '血吸虫肝病': {
        'html': '<div class="rpt-sec">肝脏形态尚规则/不规则，大小正常/增大/缩小，表面不/欠光滑，肝实质点状回声增粗，分布不均匀,呈网格状/地图状改变。</div>\n<div class="rpt-sec">CDFI：示血流信号减少。</div>',
        'fields': {},
    },
    '副脾': {
        'html': '<div class="rpt-sec">脾门区可见一等回声结节，大小约 x{_size_0}mm，形态规则，边界清，内回声均匀。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '双肾多发结石': {
        'html': '<div class="rpt-sec">双肾集合系内可见多个强回声团，伴声影，较大分别约 x{_别约_0}mm（左肾）、 x{_左肾_1}mm（右肾），无液性暗区。</div>',
        'fields': {"_别约_0": "大分别约 x", "_左肾_1": "左肾）、 x"},
    },
    '双肾多发结石。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '左肾/右肾/双肾结石伴轻度/中度积水。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '双肾多发囊肿': {
        'html': '<div class="rpt-sec">双肾实质内可见多个无回声区，壁薄，后壁回声增强，内透声可，较大分别约 x{_别约_0}mm（左肾）、 x{_左肾_1}mm（右肾）。</div>',
        'fields': {"_别约_0": "大分别约 x", "_左肾_1": "左肾）、 x"},
    },
    '肾错构瘤': {
        'html': '<div class="rpt-sec">双肾/右肾/左肾实质内见高回声结节，边界尚清，形态尚规则，内部回声欠均匀，大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '双肾/右肾/左肾高回声结节，考虑错构瘤。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '肾囊肿并囊壁钙化': {
        'html': '<div class="rpt-sec">双肾/右肾/左肾实质内见无回声区，大小约 x{_size_0}mm，壁薄，后壁回声增强，壁上可见强回声点。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '胆囊胆固醇结晶': {
        'html': '<div class="rpt-sec">胆囊形态规则，大小正常，壁稍毛糙，见多个附壁强回声点，其一大小约2x2{_size_0}mm，后伴彗尾征，改变体位不移动，胆总管上段内径正常。</div>',
        'fields': {"_size_0": "大小约2x2"},
    },
    '脂肪肝（中-重）': {
        'html': '<div class="rpt-sec">肝脏增大，形态规则，轮廓欠清，表面光滑, 实质回声分布不均匀,近场回声增强，远场回声衰减，肝内管系显示不清。</div>',
        'fields': {},
    },
    '脂肪肝（轻度）': {
        'html': '<div class="rpt-sec">肝脏形态大小正常，表面光滑, 实质回声分布欠均匀,近场回声稍增强，远场回声略衰减，肝内管系显示尚清。</div>',
        'fields': {},
    },
    '胆泥沉积': {
        'html': '<div class="rpt-sec">胆囊大小形态正常/增大，壁欠光滑，内透声差/欠佳，内可见多个强回声点堆积，范围{_范围_0}mm，改变体位可移动，胆总管上段内径正常。</div>',
        'fields': {"_范围_0": "点堆积，范围"},
    },
    '胆囊结石（单发）': {
        'html': '<div class="rpt-sec">胆囊大小形态正常，壁欠光滑，内见一强回声团,大小约 x{_size_0}mm，后伴声影，改变体位可移动，胆总管上段内径正常。</div>',
        'fields': {"_size_0": ",大小约 x"},
    },
    '肝内多发钙化灶': {
        'html': '<div class="rpt-sec">肝内可见多个强回声斑，后无声影，其一大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "一大小约 x"},
    },
    '正常腹部（门静脉）': {
        'html': '<div class="rpt-sec">门静脉内径、走行正常，管腔内透声可，内未见明显异常回声。</div>',
        'fields': {},
    },
    '门静脉未见明显异常声像。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '肾泥沙样结石': {
        'html': '<div class="rpt-sec">双肾/右肾/左肾集合系内见多个细小强回声点，后方声影不明显，无液性暗区。</div>',
        'fields': {},
    },
    '胆囊息肉样病变（单发）': {
        'html': '<div class="rpt-sec">胆囊大小形态正常，壁欠光滑，内见附壁稍高回声结节，大小约x{_size_0}mm，无声影，改变体位不移动，胆总管上段内径正常。</div>',
        'fields': {"_size_0": "节，大小约x"},
    },
    '胆囊毛糙': {
        'html': '<div class="rpt-sec">胆囊内径正常，壁稍毛糙，呈折叠状，透声可，胆囊内未见明显异常回声。</div>',
        'fields': {},
    },
    '胆囊多发息肉，考虑胆固醇结晶（陈）': {
        'html': '<div class="rpt-sec">胆囊大小形态正常，壁欠光滑，内见多个附壁稍高回声结节，无声影，不随体位改变而移动，较大约x{_大约_0}mm，胆总管上段内径正常。</div>',
        'fields': {"_大约_0": "动，较大约x"},
    },
    '双肾结石': {
        'html': '<div class="rpt-sec">双肾集合系内均可见强回声团，伴声影，其大小分别约 x{_size_0}mm（左肾）、 x{_左肾_1}mm（右肾），无液性暗区。</div>',
        'fields': {"_size_0": "小分别约 x", "_左肾_1": "左肾）、 x"},
    },
    '双肾结石。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '双肾囊肿': {
        'html': '<div class="rpt-sec">双肾实质内均可见无回声区，壁薄，后壁回声增强，内透声可，其大小分别约 x{_size_0}mm（左肾）、 x{_左肾_1}mm（右肾）。</div>',
        'fields': {"_size_0": "小分别约 x", "_左肾_1": "左肾）、 x"},
    },
    '肠气干扰（显示不清）': {
        'html': '<div class="rpt-sec">受大量肠气干扰，部分切面显示不清。</div>\n<b class="rpt-label">所示切面：</b>',
        'fields': {},
    },
    '胆囊胆固醇结晶（陈）': {
        'html': '<div class="rpt-sec">胆囊大小形态正常，壁欠光滑，内见附壁稍高回声结节，大小约x{_size_0}mm，无声影，改变体位不移动，胆总管上段内径正常。</div>',
        'fields': {"_size_0": "节，大小约x"},
    },
    '正常肾动脉模板': {
        'html': '<div class="rpt-sec">双肾形态规则，左肾大小约x{_size_0}mm，右肾大小约x{_size_1}mm，实质回声低于同水平肝脾；</div>\n<div class="rpt-sec">双肾集合系统无分离，内未见异常声像。</div>',
        'fields': {"_size_0": "左肾大小约x", "_size_1": "右肾大小约x"},
    },
    '双肾、双肾动脉及腹主动脉血流测值正常范围。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '肝内胆管积气': {
        'html': '<div class="rpt-sec">右肝前叶/右肝后叶，左肝内叶/左肝外叶见沿胆管分布的强光带，后伴彗尾征，范围约 x{_围约_0}mm。</div>',
        'fields': {"_围约_0": "，范围约 x"},
    },
    '肝内胆管部分泥沙结石部分积气': {
        'html': '<div class="rpt-sec">左肝/右肝内见沿胆管分布的多条强回声带，部分伴声影，范围约 x{_围约_0}mm，部分后伴彗尾征，范围约 x{_围约_1}mm。</div>',
        'fields': {"_围约_0": "，范围约 x", "_围约_1": "，范围约 x"},
    },
    '胆囊结石嵌顿并胆囊肿大': {
        'html': '<div class="rpt-sec">胆囊增大，大小{_size_0}mm，壁欠光滑，胆囊颈部似可见/可见一强光团，大小约，不随体位改变移动，胆总管上段内径正常/增宽，宽{_width_1}mm。</div>',
        'fields': {"_size_0": "囊增大，大小", "_width_1": "常/增宽，宽"},
    },
    '脂肪肝': {
        'html': '<div class="rpt-sec">肝脏形态大小正常，表面光滑, 实质回声分布欠均匀,近场回声增强，远场回声衰减，肝内管系显示欠清。</div>',
        'fields': {},
    },
    '建议憋尿复查（女）': {
        'html': '<b class="rpt-label">（建议憋尿复查或腔内超声检查，自行放弃检查）</b>',
        'fields': {},
    },
    '建议憋尿复查（男）': {
        'html': '<div class="rpt-sec">膀胱无尿，膀胱及前列腺显示不清。</div>\n<b class="rpt-label">（建议憋尿复查，自行放弃检查）</b>',
        'fields': {},
    },
    '肝内低回声区 考虑脂肪沉积': {
        'html': '<div class="rpt-sec">胆囊窝旁可见一大小约 x{_size_0}mm低回声区，形态欠规则，边界清，回声欠均匀。</div>',
        'fields': {"_size_0": "一大小约 x"},
    },
    '肝内低回声区 考虑非均质性脂肪肝': {
        'html': '<div class="rpt-sec">肝内可见片状低回声区，大小约 x{_size_0}mm，形态不规则，边界清，回声欠均匀。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '胆囊强回声斑，考虑壁结石或胆固醇结晶。': {
        'html': '<div class="rpt-sec">胆囊大小正常，壁光滑，透声可，内可见附壁强回声斑，伴彗尾征，大小约x{_size_0}mm，胆总管上段内径正常。</div>',
        'fields': {"_size_0": "征，大小约x"},
    },
    '肝脂肪浸润': {
        'html': '<div class="rpt-sec">肝内可见稍高/稍低/等回声结节，大小约 x{_size_0}mm，形态规则，边界尚清，内部回声欠均匀，内呈网格状改变，后方回声无衰减。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '膀胱少尿': {
        'html': '<div class="rpt-sec">膀胱充盈欠佳，壁欠光滑，内显示欠清，未见明显强回声团。</div>\n<div class="rpt-sec">前列腺形态规则，大小正常,实质回声均匀,内未见明显包块回声。</div>\n<div class="rpt-sec">CDFI:所检脏器未见明显异常血流信号。</div>',
        'fields': {},
    },
    '肝大': {
        'html': '<b class="rpt-label">右肝斜{_肝斜_0}mm，肋下{_diameter_1}mm，左肝上下{_上下_2}mm，前后{_diameter_3}mm，</b>',
        'fields': {"_肝斜_0": "右肝斜", "_diameter_1": "径mm，肋下", "_上下_2": "m，左肝上下", "_diameter_3": "径mm，前后"},
    },
    '肝实质光点增粗': {
        'html': '<b class="rpt-label">实质光点增粗，</b>',
        'fields': {},
    },
    '脂肪肝（重）': {
        'html': '<div class="rpt-sec">肝脏增大，形态饱满，轮廓欠清，表面光滑, 实质回声分布不均匀，呈云雾状,近场回声增强，远场回声衰减，肝内管系、远场肝组织及包膜显示不清。</div>',
        'fields': {},
    },
    '胆囊结石、胆囊炎': {
        'html': '<div class="rpt-sec">胆囊大小形态正常，壁欠光滑，内见一强回声团，大小约 x{_size_0}mm，后伴声影，改变体位可移动，胆总管上段内径正常。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '胆囊充填型结石、胆囊炎-CH': {
        'html': '<div class="rpt-sec">胆囊轮廓尚清，胆汁透声消失，内充满强光团，后方伴大片声影，胆总管上段内径正常。</div>',
        'fields': {},
    },
    '脾内钙化灶': {
        'html': '<div class="rpt-sec">脾内可见一大小约 x{_size_0}mm强回声斑。</div>',
        'fields': {"_size_0": "一大小约 x"},
    },
    '脾囊肿': {
        'html': '<div class="rpt-sec">脾内可见无回声区，大小约 x{_size_0}mm，壁薄，后壁回声增强，内透声可。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '脾大/脾正常高值': {
        'html': '<b class="rpt-label">脾厚{_thick_0}mm，长径{_length_1}mm，肋缘下{_length_2}mm，</b>',
        'fields': {"_thick_0": "脾厚", "_length_1": " mm，长径", "_length_2": "mm，肋缘下"},
    },
    '折叠胆囊': {
        'html': '<b class="rpt-label">呈折叠状，</b>',
        'fields': {},
    },
    '肝囊肿-CH': {
        'html': '<div class="rpt-sec">左肝内叶/左肝外叶/右肝前叶/右肝后叶可见囊性结节，大小约 x{_size_0}mm，壁薄，后壁回声增强，内透声可。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '肝多发囊肿-CH': {
        'html': '<div class="rpt-sec">肝内可见多个囊性结节，较大位于左肝内叶/左肝外叶/右肝前叶/右肝后叶，大小约 x{_size_0}mm，壁薄，后壁回声增强，内透声可。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '肝内钙化灶-CH': {
        'html': '<div class="rpt-sec">左肝内叶/左肝外叶/右肝前叶/右肝后叶可见强回声斑，大小约 x{_size_0}mm，后无声影。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '肝多发钙化灶-CH': {
        'html': '<div class="rpt-sec">肝内可见多个强回声斑，后无声影，较大位于左肝内叶/左肝外叶/右肝前叶/右肝后叶，大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '胆囊测值小': {
        'html': '<div class="rpt-sec">胆囊大小约 x{_size_0}mm，内显示不清，胆总管上段内径正常。</div>',
        'fields': {"_size_0": "囊大小约 x"},
    },
    '海绵肾-CH': {
        'html': '<b class="rpt-label">双肾髓质增大、回声增强，呈放射状排列</b>',
        'fields': {},
    },
    '脾血管瘤': {
        'html': '<div class="rpt-sec">脾内可见稍高/稍低/等回声结节，大小约 x{_size_0}mm，形态规则，边界尚清，内部回声欠均匀，内呈“网格状”改变，后方回声无衰减。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '门静脉海绵样变.': {
        'html': '<div class="rpt-sec">肝内可见混合回声区，大小约x{_size_0}mm，形态规则，边界尚清，内部回声欠均匀，内呈“网格状”改变，后方回声无衰减。</div>\n<div class="rpt-sec">CDFI:肝内混合回声区内可见红蓝相间血流,内探及门静脉频谱。</div>',
        'fields': {"_size_0": "区，大小约x"},
    },
    '脾大': {
        'html': '<b class="rpt-label">脾{_脾_0}mm，长{_thick_1}mm，肋下{_length_2}mm,</b>',
        'fields': {"_脾_0": "脾", "_thick_1": "脾厚mm，长", "_length_2": "径mm，肋下"},
    },
    '双肾盂-LD': {
        'html': '<div class="rpt-sec">左/右肾内可见一宽{_width_0}mm低回声带将集合系统分隔成上下独立两部分</div>',
        'fields': {"_width_0": "肾内可见一宽"},
    },
    '膀胱充盈差': {
        'html': '<div class="rpt-sec">膀胱充盈差，所示切面未见明显异常回声。</div>',
        'fields': {},
    },
    '多囊肾': {
        'html': '<div class="rpt-sec">双肾形态失常、增大，实质内可见密集分布、大小不等的囊性结节，较大者大小约</div>',
        'fields': {},
    },
    '正常腹部（无门静脉）': {
        'html': '<div class="rpt-sec">肝脏形态规则，大小正常，表面光滑， 实质回声分布均匀，肝内管系尚清。</div>',
        'fields': {},
    },
    '结石？钙化（申）': {
        'html': '<div class="rpt-sec">左/右/双肾见强回声点，后方声影不明显，大小约 x{_size_0}mm。</div>\n<div class="rpt-sec">双肾集合系无明显分离。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '正常腹部（无门静脉，申）': {
        'html': '<div class="rpt-sec">肝脏形态规则，大小正常，表面光滑， 实质回声分布均匀，肝内管系尚清。</div>',
        'fields': {},
    },
    '肝、胆、脾、胰、双肾，输尿管内未见明显异常声像。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '肝脏脂肪沉积(xy)': {
        'html': '<div class="rpt-sec">肝脏形态规则，大小正常，表面光滑，实质光点细密，回声分布均匀，肝内管系尚清。</div>',
        'fields': {},
    },
}

register_templates(_TPL, category='腹部')
