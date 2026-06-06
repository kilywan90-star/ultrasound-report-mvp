"""自动生成 — obstetrics 结构化模板"""
from template_converted import register_templates

_TPL = {
    '胎儿': {
        'html': '<b class="rpt-label">胎儿</b>',
        'fields': {},
    },
    '宫内单活胎声像': {
        'html': '<div class="rpt-sec">子宫形态饱满，体积增大，宫腔内可见一胎儿声像，胎动及胎心搏动可见。</div>',
        'fields': {},
    },
    '宫内妊娠单活胎1': {
        'html': '<div class="rpt-sec">子宫增大，宫腔内可见一胎儿声像，可见胎动及胎心搏动。</div>',
        'fields': {},
    },
}

register_templates(_TPL, category='产科')
