"""自动生成 — urology 结构化模板"""
from template_converted import register_templates

_TPL = {
    '前列腺钙化灶': {
        'html': '<div class="rpt-sec">内见强回声斑。</div>',
        'fields': {},
    },
    '前列腺多发钙化灶': {
        'html': '<div class="rpt-sec">内见多个强回声斑。</div>',
        'fields': {},
    },
    '前列腺稍大': {
        'html': '<div class="rpt-sec">前列腺大小约 xx{_size_0}mm，形态稍饱满，实质回声欠均匀，内未见明显包块回声。</div>',
        'fields': {"_size_0": "大小约 xx"},
    },
    '前列腺增生并钙化灶': {
        'html': '<div class="rpt-sec">前列腺大小约 xx{_size_0}mm，形态饱满，实质回声欠均匀，内见强回声斑，后伴弱声影。</div>',
        'fields': {"_size_0": "大小约 xx"},
    },
    '睾丸及附睾': {
        'html': '<div class="rpt-sec">双侧睾丸大小分别约 xx{_size_0}mm(L），xx{_m_1}mm(R)，形态规则，实质回声均匀，未见明显肿块回声。</div>',
        'fields': {"_size_0": "分别约 xx", "_m_1": "(L），xx"},
    },
    '双侧睾丸及附睾未见明显异常。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '睾丸 附睾': {
        'html': '<div class="rpt-sec">双侧睾丸形态规则，表面光滑，大小正常，实质回声均匀，未见明显肿块回声。</div>',
        'fields': {},
    },
    '前列腺囊肿': {
        'html': '<div class="rpt-sec">内可见一无回声区，壁薄，后壁回声增强，内透声可，大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '双侧精囊腺稍大（陈）': {
        'html': '<div class="rpt-sec">双侧精囊腺形态饱满，体积稍大，回声均匀，左侧厚{_thick_0}mm，右侧厚{_thick_1}mm。</div>',
        'fields': {"_thick_0": "均匀，左侧厚", "_thick_1": "mm，右侧厚"},
    },
    '膀胱': {
        'html': '<div class="rpt-sec">膀胱欠充盈，内部结构显示不清。</div>',
        'fields': {},
    },
    '前列腺增生': {
        'html': '<div class="rpt-sec">前列腺大小约 xx{_size_0}mm，形态饱满，实质回声欠均匀，内未见明显包块回声。</div>',
        'fields': {"_size_0": "大小约 xx"},
    },
    '双侧精索静脉曲张、腹股沟疝': {
        'html': '<div class="rpt-sec">双侧睾丸上方可见迂曲管状暗区，较宽处{_width_0}mm（左），{_width_1}mm（右）。</div>',
        'fields': {"_width_0": "暗区，较宽处", "_width_1": "mm（左），"},
    },
    '附睾头囊肿': {
        'html': '<div class="rpt-sec">右/左侧附睾头内可见无回声区，形态规则，边界清晰，内透声可，大小约x{_size_0}mm。</div>',
        'fields': {"_size_0": "可，大小约x"},
    },
    '膀胱憩室': {
        'html': '<div class="rpt-sec">膀胱壁可见 x{_可见_0}mm的无回声区，边界清，透声可，与膀胱部分相通。</div>',
        'fields': {"_可见_0": "胱壁可见 x"},
    },
    '膀胱无回声区，考虑膀胱憩室。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '双侧睾丸鞘膜腔积液': {
        'html': '<div class="rpt-sec">双侧睾丸鞘膜腔可见液暗区，大小约x{_size_0}mm（右）、x{_约右_1}mm（左）。</div>',
        'fields': {"_size_0": "区，大小约x", "_约右_1": "m（右）、x"},
    },
    '睾丸微石症': {
        'html': '<div class="rpt-sec">双侧睾丸内可见多个细小强回声斑。</div>',
        'fields': {},
    },
    '正常男性膀胱前列腺': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '膀胱、前列腺未见明显异常声像。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '前列腺低回声结节': {
        'html': '<div class="rpt-sec">内可见低回声结节,形态规则，边界清晰，内部回声欠均匀，大小约x{_size_0}mm。</div>',
        'fields': {"_size_0": "匀，大小约x"},
    },
    '前列腺稍大-ch': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺稍大。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '左侧/右侧睾丸内强回声点，考虑睾丸微石症可能。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '前列腺钙化灶CH': {
        'html': '<div class="rpt-sec">内可见强回声斑，大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "，大小约 x"},
    },
    '前列腺多发钙化灶CH': {
        'html': '<div class="rpt-sec">内见多个强回声斑，较大者大小约 x{_size_0}mm。</div>',
        'fields': {"_size_0": "者大小约 x"},
    },
    '前列腺增生-ch': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺增生。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '前列腺稍大并钙化灶-ch': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺稍大并钙化灶。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '前列腺增生并钙化灶-ch': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺增生并钙化灶。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '前列腺增生并多发钙化灶-CH': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺增生并多发钙化灶。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '前列腺增大': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺增大。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '前列腺钙化灶-申': {
        'html': '<div class="rpt-sec">膀胱充盈可/一般/差，壁光滑/毛糙/欠光滑，部分显示欠清，显示部分内/内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺多发钙化灶-申': {
        'html': '<div class="rpt-sec">膀胱充盈可/一般/差，壁光滑/毛糙/，显示部分内/内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺增大并钙化灶-申': {
        'html': '<div class="rpt-sec">膀胱充盈可/一般/差，壁光滑/毛糙/欠光滑，部分显示欠清，显示部分内/内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺增大并多发钙化-申': {
        'html': '<div class="rpt-sec">膀胱充盈可/一般/差，壁光滑/毛糙/欠光滑，部分显示欠清，显示部分内/内未见明显包块回声。</div>',
        'fields': {},
    },
    '膀胱血块（附二）': {
        'html': '<div class="rpt-sec">膀胱形态轮廓正常，其内可见一个 大小约 ×{_size_0}mm的异常低回声，形状不规则，改变体位可移动。</div>',
        'fields': {"_size_0": " 大小约 ×"},
    },
    '膀胱结石。（附二）': {
        'html': '<div class="rpt-sec">膀胱切面形态轮廓正常，其内可见一个大小约 ×{_size_0}mm的强回声光团，后方伴声影，改变体位可移动。</div>',
        'fields': {"_size_0": "个大小约 ×"},
    },
    '膀胱内结石。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '膀胱三角区异常实质性回声，性质待查，考虑膀胱肿瘤：表浅型。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '膀胱内异物(附二)': {
        'html': '<div class="rpt-sec">膀胱形态轮廓正常，其内可见一个大小约 ×{_size_0}mm的异常回声，形状呈管状，内部为强回声，后方有声影，改变体位可移动。</div>',
        'fields': {"_size_0": "个大小约 ×"},
    },
    '膀胱憩室(附二)': {
        'html': '<div class="rpt-sec">膀胱切面形态轮廓正常，在膀胱左侧壁外紧靠膀胱可见一个大小约 ×{_size_0}mm的异常无回声，形状呈圆形，壁薄光滑，内呈一致性暗区，与膀胱相通，排尿后此异常暗区缩小。</div>',
        'fields': {"_size_0": "个大小约 ×"},
    },
    '前列腺钙化灶-zlf': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺钙化灶。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
    '前列腺稍大并钙化灶-zlf': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺增大并钙化灶-zlf': {
        'html': '<div class="rpt-sec">膀胱充盈可，壁光滑，内未见明显包块回声。</div>',
        'fields': {},
    },
    '前列腺增大并钙化灶。': {
        'html': '<b class="rpt-label">0</b>',
        'fields': {},
    },
}

register_templates(_TPL, category='泌尿')
