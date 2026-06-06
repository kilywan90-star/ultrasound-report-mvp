"""结构化超声模板引擎 — 选项组定义"""
# 格式: [(regex, option_key), ...]
# 互斥组通过共享前缀的 _A, _B, _C 后缀自动识别

# === 通用选项（适用于多数模板） ===
COMMON = [
    # 形态
    (r"形态规则|形态正常|轮廓规则", "shape_reg"),
    (r"形态不规则|轮廓不规则|变形", "shape_irreg"),
    # 边界
    (r"边界清晰|边界清楚|边界清", "border_clear"),
    (r"边界模糊|边界不清|边界欠清|边界模糊不清", "border_unclear"),
    # 回声
    (r"回声均匀|回声分布均匀", "echo_homo"),
    (r"回声不均匀|回声欠均匀|回声分布不均匀|回声欠均", "echo_hetero"),
    # 包膜/表面
    (r"包膜光整|包膜光滑|表面光滑|表面光整", "capsule_smooth"),
    (r"包膜不光滑|包膜欠光滑|表面粗糙", "capsule_rough"),
    # 壁
    (r"壁光滑|壁光整|壁规整", "wall_smooth"),
    (r"壁毛糙|壁欠光滑|壁增厚|壁粗糙", "wall_rough"),
    # 内部
    (r"内部回声均匀", "inner_homo"),
    (r"内部回声不均匀|内部回声欠均匀", "inner_hetero"),
    # 后方
    (r"后方回声无衰减|后方回声正常", "rear_normal"),
    (r"后方回声增强|后方回声衰减|后方伴声影", "rear_abnormal"),
    # 血流
    (r"CDFI.*未见.*血流|CDFI.*无.*血流|未见血流信号", "cdfi_none"),
    (r"CDFI.*可见.*血流|CDFI.*血流信号|血彩丰富|点条状血流", "cdfi_present"),
    # 占位
    (r"未见(?:明显)?占位|未见(?:明显)?异常|未探及|未见", "mass_none"),
    (r"可见.*占位|探及.*回声|可见.*结节|可见.*团块", "mass_present"),
]

# === 腹部 ===
ABDOMEN = [
    (r"肝脏(?:大小|形态)?正常|肝脏未见异常", "liver_normal"),
    (r"肝脏(?:体积|大小)\s*增大|肝大|肝下移|肝脏饱满", "liver_enlarged"),
    (r"肝脏回声.*增强.*增粗|回声.*增粗.*增强", "liver_coarse"),
    (r"肝内管系.*清|肝内血管.*清|肝内管道.*清", "liver_duct_clear"),
    (r"肝内管系.*不清|肝内血管.*模糊", "liver_duct_unclear"),
    (r"胆囊.*充满型|胆囊充填.*", "gall_filled"),
    (r"胆囊.*多发|多个", "gall_multi"),
    (r"胆囊.*单发|单个", "gall_single"),
    (r"胆囊.*(?:切除|术后)", "gall_postop"),
    (r"随体位移动|移动(?:性)?可", "mobile"),
]

# === 心脏 ===
CARDIAC = [
    (r"各房室(?:大小|内径)正常|房室不大", "chamber_normal"),
    (r"心室.*增大|心房.*增大|房室.*扩大|心腔.*增大", "chamber_enlarged"),
    (r"室壁.*不厚|室壁.*正常|室间隔.*不厚", "wall_normal"),
    (r"室壁.*增厚|室间隔.*增厚|左室壁.*肥厚", "wall_thick"),
    (r"室壁.*增厚|室间隔.*增厚|左室壁.*肥厚", "wall_thick"),
    (r"运动协调|运动正常|运动未见异常", "wall_motion_normal"),
    (r"运动.*减弱|运动.*低平|运动.*消失|室壁.*矛盾", "wall_motion_abnormal"),
    (r"各瓣膜.*清晰|瓣膜.*启闭自如|瓣膜.*正常", "valve_normal"),
    (r"瓣膜.*增厚|瓣膜.*钙化|瓣膜.*回声增强|瓣膜.*粘连", "valve_abnormal"),
    (r"未见.*返流|无.*返流|未见.*反流", "regurg_none"),
    (r"轻度.*返流|少量.*返流|轻度.*反流", "regurg_mild"),
    (r"中度.*返流|中量.*返流", "regurg_moderate"),
    (r"重度.*返流|大量.*返流", "regurg_severe"),
    (r"心包.*未见|心包腔.*无.*积液|心包.*正常", "pericard_normal"),
    (r"心包.*积液|心包腔.*液性", "pericard_effusion"),
]

# === 甲状腺 ===
THYROID = [
    (r"甲状腺.*(?:形态|大小)正常|甲状腺未见异常", "thyroid_normal"),
    (r"甲状腺.*增大|甲状腺肿大|甲大", "thyroid_enlarged"),
    (r"甲状腺.*弥漫.*病变|弥漫.*回声.*不均", "thyroid_diffuse"),
    (r"结节.*边界清|结节.*边界清晰", "nodule_border_clear"),
    (r"结节.*边界不清|结节.*边界模糊", "nodule_border_unclear"),
    (r"结节.*钙化|钙化灶|钙化点", "nodule_calcify"),
    (r"结节.*囊性|囊实性|囊变", "nodule_cystic"),
]

# === 乳腺 ===
BREAST = [
    (r"乳腺.*未见.*占位|双乳.*未见.*异常|乳腺.*正常", "breast_normal"),
    (r"乳腺.*增生|小叶增生|乳腺组织增厚", "breast_hyperplasia"),
    (r"结节.*形态规则|结节.*规则", "nodule_shape_regular"),
    (r"结节.*形态不规则|结节.*不规则", "nodule_shape_irregular"),
    (r"结节.*(?:无|没有)钙化|未见.*钙化", "nodule_no_calcify"),
]

# === 全部合并 ===
ALL = {
    "common": COMMON,
    "abdomen": ABDOMEN,
    "cardiac": CARDIAC,
    "thyroid": THYROID,
    "breast": BREAST,
}
