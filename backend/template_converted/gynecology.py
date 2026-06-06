"""自动生成 — gynecology 结构化模板"""
from template_converted import register_templates

_TPL = {
    '女性经阴道彩超（子宫附件）': {
        'html': '<div class="rpt-sec">子宫前位，形态规则，大小正常，实质回声均匀，宫腔线居中，内膜厚{_thick_0}mm，宫内未见明显异常光团及暗区。</div>',
        'fields': {"_thick_0": "居中，内膜厚"},
    },
    '子宫、附件未见明显异常声像。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '双侧卵巢多囊样改变': {
        'html': '<div class="rpt-sec">右侧卵巢大小约 x{_size_0}mm，左侧卵巢大小约 x{_size_1}mm，双侧卵巢同一切面内可见大于十个小囊泡声像，直径约7-9{_diameter_2}mm。</div>',
        'fields': {"_size_0": "巢大小约 x", "_size_1": "巢大小约 x", "_diameter_2": "直径约7-9"},
    },
    '宫颈囊肿': {
        'html': '<div class="rpt-sec">宫颈内可见无回声区，大小约 x{_size_0}mm，壁薄，后壁回声增强，内透声可。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '宫颈多发囊肿': {
        'html': '<div class="rpt-sec">宫颈内可见多个无回声区，较大约 x{_大约_0}mm，壁薄，后壁回声增强，内透声可。</div>',
        'fields': {"_大约_0": "，较大约 x"},
    },
    '子宫肌瘤': {
        'html': '<div class="rpt-sec">子宫前壁/后壁可见低回声结节，大小约 x{_size_0}mm，形态规则，边界清晰，内部回声欠均匀。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '子宫多发肌瘤': {
        'html': '<div class="rpt-sec">子宫前壁/后壁内可见多个低回声结节，较大约 x{_大约_0}mm，形态规则，边界清晰，内部回声欠均匀。</div>',
        'fields': {"_大约_0": "，较大约 x"},
    },
    '卵巢囊肿': {
        'html': '<div class="rpt-sec">左侧/右侧卵巢可见无回声区，壁薄，内壁光滑，内透声可，后壁回声增强，大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '子宫内膜声像改变': {
        'html': '<div class="rpt-sec">子宫前位/平位/后位，大小约xx{_size_0}mm，内膜{_内膜_1}mm，局限性/弥漫性回声增强，子宫肌层为非均质性低回声，内部点状回声增粗。</div>',
        'fields': {"_size_0": "，大小约xx", "_内膜_1": " mm，内膜"},
    },
    '子宫内膜声像改变，性质待定。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '子宫肌瘤伴囊性变': {
        'html': '<div class="rpt-sec">子宫前位/平位/后位，大小约 xx{_size_0}mm，内膜{_内膜_1}mm，前壁/后壁见大小约 x{_size_2}mm混合性结节，形态规则，边界清晰，内部回声不均匀，见不规则无回声区/强回声区。</div>',
        'fields': {"_size_0": "大小约 xx", "_内膜_1": " mm，内膜", "_size_2": "见大小约 x"},
    },
    '子宫肌瘤伴囊性变/钙化。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '子宫腺肌症': {
        'html': '<div class="rpt-sec">肌壁增厚，点状回声增粗，宫腔线前移。</div>',
        'fields': {},
    },
    '附件区囊肿': {
        'html': '<div class="rpt-sec">左侧/右侧附件区可见无回声区，壁薄，内壁光滑，内透声可，后壁回声增强，大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '盆腔积液': {
        'html': '<div class="rpt-sec">子宫直肠窝可见范围约 x{_围约_0}mm液性暗区。</div>',
        'fields': {"_围约_0": "见范围约 x"},
    },
    '宫颈管积液': {
        'html': '<div class="rpt-sec">宫颈管内可见宽{_width_0}mm液暗区。</div>',
        'fields': {"_width_0": "颈管内可见宽"},
    },
    '巧克力囊肿': {
        'html': '<div class="rpt-sec">左侧/右侧卵巢可见无回声结节，形态规则，边界清，内透声差，可见细密点状回声，大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '宫内早孕': {
        'html': '<div class="rpt-sec">子宫前位，形态规则，大小正常，实质回声均匀，宫腔内可见大小约 x{_size_0}mm孕囊声像，内可见卵黄囊及胚芽组织，长{_织长_1}mm,原始心管搏动可见。</div>',
        'fields': {"_size_0": "见大小约 x", "_织长_1": "胚芽组织，长"},
    },
    '子宫切口假腔': {
        'html': '<div class="rpt-sec">子宫前壁切口处可见不规则暗区，范围约x{_围约_0}mm，与宫腔相通。</div>',
        'fields': {"_围约_0": "区，范围约x"},
    },
    '子宫内膜息肉样病变': {
        'html': '<div class="rpt-sec">宫腔内可见一大小约x{_size_0}mm稍高回声结节，形态规则，边界清，内回声欠均匀。</div>',
        'fields': {"_size_0": "见一大小约x"},
    },
    '宫腔内稍高回声结节，考虑内膜息肉样病变。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '子宫假腔': {
        'html': '<div class="rpt-sec">子宫前壁下段可见积液暗区，范围约x{_围约_0}mm，与宫腔相通，距前壁浆膜层距离{_距离_1}mm。</div>',
        'fields': {"_围约_0": "区，范围约x", "_距离_1": "壁浆膜层距离"},
    },
    '绝经后子宫声像': {
        'html': '<div class="rpt-sec">子宫前位，形态规则，体积缩小，实质回声均匀，宫腔线居中，内膜呈线状。</div>',
        'fields': {},
    },
    '绝经后子宫声像。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '宫内妊娠单活胎2': {
        'html': '<div class="rpt-sec">子宫增大，形态饱满，实质回声均匀，宫腔内可见孕囊声像，内可见一胚胎，头臀长{_臀长_0}mm，可见胎动及胎声搏动。</div>',
        'fields': {"_臀长_0": "胚胎，头臀长"},
    },
    '正常女性膀胱子宫附件': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '膀胱、子宫、附件未见明显异常声像。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '子宫萎缩-ch': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '子宫萎缩。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '绝经后子宫': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '宫颈钙化灶': {
        'html': '<div class="rpt-sec">宫颈内可见强回声斑，大小约x{_size_0}mm，伴声影。</div>',
        'fields': {"_size_0": "斑，大小约x"},
    },
    '内膜稍毛糙。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '双侧颈动脉内膜面稍毛糙。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '子宫萎缩-CH': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '绝经后子宫声像-MYY': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '正常腹主动脉': {
        'html': '<div class="rpt-sec">腹主动脉内径正常，内膜光滑、未增厚，内未见明显异常回声。</div>',
        'fields': {},
    },
    '腹主动脉斑块': {
        'html': '<div class="rpt-sec">腹主动脉内径正常，内膜毛糙，管壁增厚，腹主动脉内可见低/等/强/不均质回声斑块，大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '老年性子宫-LD': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '老年性子宫声像。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '双下肢动脉硬化并多发斑块形成(附二)': {
        'html': '<div class="rpt-sec">双侧下肢动脉（髂外、髂股段、股、股浅、股深、腘、胫后、胫前、足背A）走行正常，管壁增厚，内膜面回声毛糙，内-中膜较厚处{_thick_0}mm，双下肢动脉内可见多个附壁强光团，较大者分别约 ×{_别约_1}mm（右）、 ×{_右_2}mm（左）。</div>',
        'fields': {"_thick_0": "-中膜较厚处", "_别约_1": "者分别约 ×", "_右_2": "（右）、 ×"},
    },
    '双上肢动脉硬化并多发斑块形成': {
        'html': '<div class="rpt-sec">双侧上肢（腋、肱、尺、桡动脉）走行正常，管壁增厚，内膜面回声毛糙，内-中膜较厚处{_thick_0}mm，双上肢动脉内可见多个附壁强光团，较大者分别约  x{_别约_1}mm（右）、 x{_右_2}mm（左）。</div>',
        'fields': {"_thick_0": "-中膜较厚处", "_别约_1": "分别约  x", "_右_2": "（右）、 x"},
    },
    '子宫发育畸形，双角子宫？（附二）': {
        'html': '<div class="rpt-sec">子宫前/后/平位，大小约 xx{_size_0}mm，横切面宫底增宽，呈“心形”凹陷，可见两个内膜回声，于宫腔上/中/下段融合，厚{_thick_1}mm，可见一个/两个宫颈管。</div>',
        'fields': {"_size_0": "大小约 xx", "_thick_1": "下段融合，厚"},
    },
    '子宫发育畸形，双角子宫可能性大。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '子宫右侧肌性结构，残角子宫？（附二）': {
        'html': '<div class="rpt-sec">子宫前/后/平位，大小约xx{_size_0}mm，实质回声均匀，内膜线居中，厚{_thick_1}mm，宫内未见明显肿块声像。</div>\n<div class="rpt-sec">子宫右侧可见一大小约×{_size_2}mm肌性结构与子宫左/右侧壁相连，其中央未见/可见内膜样高回声。</div>',
        'fields': {"_size_0": "，大小约xx", "_thick_1": "膜线居中，厚", "_size_2": "见一大小约×"},
    },
    '子宫右侧肌性结构，考虑残角子宫可能性大。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '纵隔子宫？（附二）': {
        'html': '<div class="rpt-sec">子宫前/后/平位，大小约xx{_size_0}mm，实质回声均匀，横断面增宽，宫腔上段/中上段被分为左、右两部分，两侧宫角之间肌层宽{_width_1}mm，深{_width_2}mm，左右内膜厚度均{_thick_3}mm，两内膜于宫腔上/中/下段融合，宫腔内未见明显肿块声像，可见一个/两个宫颈管。</div>',
        'fields': {"_size_0": "，大小约xx", "_width_1": "角之间肌层宽", "_width_2": "宽约mm，深", "_thick_3": "右内膜厚度均"},
    },
    '子宫发育畸形，纵隔子宫可能性大。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '子宫异位征（附二）': {
        'html': '<div class="rpt-sec">盆腔未探及正常子官声像，膀胱后方可见一个低回声条索状物，大小约x{_size_0}mm，实质回声均匀，内未见明显内膜线回声。</div>',
        'fields': {"_size_0": "物，大小约x"},
    },
    '子宫异位征': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '双子宫？（附二）': {
        'html': '<div class="rpt-sec">盆腔内可见两个宫体、两个宫颈声像，两个宫腔不相通，左侧子宫前/后/平位，大小约×x{_size_0}mm，实质回声均匀，内膜线居中，厚{_thick_1}mm，宫内未见明显肿块图像。</div>\n<div class="rpt-sec">右侧子宫前/后/平位，大小约xx{_size_2}mm，实质回声均匀，内膜线居中，厚{_thick_3}mm，宫内未见明显肿块图像。</div>',
        'fields': {"_size_0": "，大小约×x", "_thick_1": "膜线居中，厚", "_size_2": "，大小约xx", "_thick_3": "膜线居中，厚"},
    },
    '巧克力囊肿（附二）': {
        'html': '<div class="rpt-sec">子宫前/后/平位，大小约xx{_size_0}mm，实质回声均匀，内膜线居中，厚{_thick_1}mm，宫内及肌壁未见明显肿块声像。</div>',
        'fields': {"_size_0": "，大小约xx", "_thick_1": "膜线居中，厚"},
    },
    '腹主动脉瘤': {
        'html': '<div class="rpt-sec">腹主动脉部分节段内径瘤样扩张，内径{_diameter_0}mm，与正常段内径比值：，其扩张段暂未见明显血栓及斑块，余管腔内膜光滑、未增厚，内未见明显异常回声。</div>',
        'fields': {"_diameter_0": "样扩张，内径"},
    },
}

register_templates(_TPL, category='妇科')
