"""批量测试超声报告结构化 — 100条测试用例"""

import json
import time
import statistics
from pathlib import Path

import httpx

API = "http://localhost:8700/api/structure"

# 100条超声口述（覆盖腹部、心脏、妇产、泌尿、小器官）
TEST_CASES = [
    # === 腹部超声 (1-25) ===
    {"text": "腹部超声检查。肝脏形态饱满，左叶前后径68mm，右叶前后径142mm，回声增粗不均匀。肝内可见一个大小约12乘10mm的无回声区，边界清晰，后方回声增强。胆囊大小正常，壁光滑，腔内未见异常回声。胰腺脾脏未见异常。超声提示：1、脂肪肝 K76.0 2、肝囊肿 建议定期复查。", "expected_organ_count": 4, "expected_diag_count": 2},
    {"text": "肝脏大小正常，被膜光滑，实质回声均匀，血管走行清晰。胆囊大小约68*28mm，壁厚2mm，光滑，腔内无回声区清晰，未见结石及占位。胆总管内径5mm。胰腺大小形态正常，回声均匀，胰管无扩张。脾脏肋间厚32mm，回声均匀。双肾大小形态正常，实质回声均匀，集合系统无分离。超声提示：腹部超声未见明显异常。", "expected_organ_count": 6, "expected_diag_count": 1},
    {"text": "胆囊大小约78*36mm，壁厚4mm、毛糙，腔内可见多个强回声团，大者约8*6mm，后伴声影，随体位改变移动。胆总管未见扩张。肝脏、胰腺、脾脏、双肾未见异常。超声提示：1、慢性胆囊炎 2、胆囊多发结石", "expected_organ_count": 6, "expected_diag_count": 2},
    {"text": "右肾上极可见一大小约45*38mm的无回声区，边界清晰，后方回声增强，内部透声好。左肾未见异常。超声提示：右肾囊肿 N28.1", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "肝脏右叶可见一大小约22*18mm的高回声结节，边界清晰，周边可见低回声晕。余肝脏实质回声均匀。超声提示：肝血管瘤 D18.0，建议定期复查。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "胰腺头颈部可见一大小约35*28mm的低回声肿块，边界模糊，形态不规则，内部回声不均匀。胰管扩张约4mm。肝内外胆管扩张不明显。超声提示：胰头占位性病变，建议CT进一步检查。", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "脾脏肋间厚约52mm，长径约138mm，形态饱满，回声均匀。肝脏左叶前后径72mm，右叶斜径148mm，回声稍增强。超声提示：1、脾大 R16.1 2、脂肪肝趋向", "expected_organ_count": 2, "expected_diag_count": 2},
    {"text": "左肾盂可见数个强回声团，大者约5*4mm，后伴声影。集合系统轻度分离约12mm。右肾未见异常。超声提示：左肾结石伴轻度肾盂积水 N20.0", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "胆囊大小约52*22mm，壁不厚。腔内可见泥沙样强回声沉积于后壁，范围约30*12mm，无声影。超声提示：胆囊泥沙样结石 K80.2", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "肝脏右叶可见一片状低回声区，范围约58*42mm，边界模糊，形态不规则。周边血管走行正常。超声提示：肝内低回声区，性质待定，建议增强CT检查。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "腹盆腔可见游离无回声区，肝肾隐窝深约18mm，脾肾隐窝深约12mm，下腹部深约25mm。超声提示：腹腔积液，建议结合临床。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "胆囊大小约90*42mm，张力高，壁厚5mm，呈双边征。腔内未见结石。超声Murphy征阳性。超声提示：急性胆囊炎 K81.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "肝脏回声弥漫性增粗，表面呈结节状，肝内血管走行紊乱。肝右叶可见一大小约15*12mm的低回声结节。脾脏肋间厚48mm。超声提示：1、肝硬化 K74.6 2、肝内低回声结节，建议增强检查 3、脾大", "expected_organ_count": 2, "expected_diag_count": 3},
    {"text": "双肾大小形态正常，实质回声均匀，集合系统无分离。左肾中部可见一大小约10*8mm的强回声团，后伴弱声影。超声提示：左肾小结石", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "肝脏右后叶可见一大小约65*52mm的混合回声肿块，边界清，内部回声不均匀，可见不规则无回声区。CDFI显示周边及内部丰富血流信号。超声提示：肝占位性病变，考虑肝癌可能，建议穿刺活检 C22.9", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "超声所见：胆总管上段扩张约10mm，管腔内可见一大小约8*6mm的强回声团，后伴声影。肝内胆管轻度扩张。超声提示：胆总管结石伴肝内外胆管扩张 K80.5", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "胰腺体积增大，头颈部厚约32mm，体尾部厚约25mm，回声减低不均匀，轮廓模糊。胰周可见少量积液。超声提示：急性胰腺炎 K85.9", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右肾体积缩小，大小约82*40mm，实质回声增强，皮髓质分界不清。左肾代偿性增大，大小约126*56mm。超声提示：右肾萎缩，左肾代偿性增大", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "膀胱充盈良好，壁光滑，腔内未见异常回声。前列腺大小约42*32*30mm，形态饱满，向膀胱内突出。超声提示：前列腺增生 N40", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "肝脏大小形态正常，实质回声均匀。胆囊切除术后，胆总管代偿性扩张约9mm。胰腺、脾脏、双肾未见异常。超声提示：胆囊切除术后改变", "expected_organ_count": 6, "expected_diag_count": 1},
    {"text": "右肾中部可见一大小约32*28mm的低回声肿块，边界清晰，内部回声欠均匀。CDFI显示周边环形血流。超声提示：右肾肿瘤，考虑肾错构瘤可能 D30.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "肝脏大小正常，实质回声不均匀增强。肝内血管显示欠清晰。超声提示：肝脏弥漫性病变，符合脂肪肝超声改变", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "脾脏肋间厚约32mm，实质内可见一大小约20*18mm的钙化灶，呈强回声伴声影。超声提示：脾脏钙化灶", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "双肾大小形态正常，左肾集合系统分离约22mm，肾盂肾盏扩张。左侧输尿管上段扩张约8mm。超声提示：左肾积水 N13.3，建议进一步检查明确梗阻原因", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "肝脏左叶可见多个大小不等的囊性无回声区，大者约45*40mm，边界清晰，后方回声增强。超声提示：多发性肝囊肿 Q44.7", "expected_organ_count": 1, "expected_diag_count": 1},

    # === 妇产超声 (26-45) ===
    {"text": "子宫前位，大小约72*52*45mm，形态规则，肌壁回声均匀，内膜厚约8mm。宫颈未见异常。双侧卵巢大小形态正常。盆腔未见游离无回声区。超声提示：子宫及双侧附件未见明显异常。", "expected_organ_count": 3, "expected_diag_count": 1},
    {"text": "子宫增大，大小约98*76*65mm，肌壁回声不均匀，前壁可见一大小约35*30mm的低回声结节，边界清晰。内膜厚约7mm。超声提示：子宫肌瘤 D25.9", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右侧卵巢可见一大小约42*38mm的无回声囊性结构，壁薄光滑，内部透声好。左侧卵巢大小形态正常。超声提示：右侧卵巢单纯性囊肿 N83.2，建议随访。", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "宫内可见一孕囊，大小约28*18mm，可见卵黄囊，胚芽长约5mm，可见原始心管搏动。超声提示：宫内早孕，约孕6周，胚胎存活。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "子宫肌壁回声不均匀，弥漫性增粗增强，以后壁为著。子宫大小约85*60*50mm。超声提示：子宫腺肌症 N80.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "左侧卵巢可见一大小约58*52mm的囊实性包块，壁厚薄不均，内部可见分隔及乳头状突起。CDFI显示分隔上可见血流信号。超声提示：左侧卵巢囊实性占位，性质待定，建议肿瘤标志物检查及MRI。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "子宫内膜厚约15mm，回声不均匀增强，内膜线不清晰。宫腔内可见一大小约10*8mm的高回声团。超声提示：子宫内膜增厚伴宫腔占位，考虑内膜息肉 N84.0，建议宫腔镜检查。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "子宫前壁下段剖宫产切口处可见一大小约25*18mm的无回声区，边界清晰，与宫腔相通。超声提示：子宫切口憩室 O34.2", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "子宫增大如孕12周大小，肌壁回声不均匀，可见多个大小不等的低回声结节，大者位于前壁约48*42mm。内膜厚约6mm。超声提示：多发性子宫肌瘤 D25.9", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右侧附件区可见一大小约38*30mm的腊肠形无回声区，壁厚，内部透声差。左侧附件区未见异常。超声提示：右侧输卵管积水 N70.1", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "宫内妊娠，胎儿双顶径约68mm，头围约248mm，腹围约225mm，股骨长约48mm。胎盘位于前壁，厚约28mm，成熟度I级。羊水指数约138mm。超声提示：宫内中期妊娠，胎儿发育符合孕25周。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "子宫后位，大小约65*45*38mm，内膜厚约4mm。宫腔内可见节育器强回声，位置正常，距宫底约12mm。超声提示：宫内节育器位置正常。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "盆腔可见大片游离无回声区，肝肾隐窝深约30mm，子宫直肠陷凹深约45mm，双侧附件区亦可见游离液体。超声提示：盆腔大量积液，请结合临床。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右侧卵巢体积增大，大小约42*28mm，可见多个大小不等的小囊泡呈车轮状排列，最大约8mm。左侧卵巢正常。超声提示：右侧卵巢多囊样改变 E28.2", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "宫颈肥大，大小约42*38mm，可见多个大小不等的囊性无回声区，大者约8mm。超声提示：宫颈肥大伴纳氏囊肿 N72", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "子宫后壁可见一大小约32*25mm的肌瘤结节，边界清晰，部分向宫腔内突出。内膜厚约7mm，受压移位。超声提示：子宫粘膜下肌瘤 D25.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "子宫内膜厚约5mm，回声均匀。宫腔内可见一大小约20*15mm的不规则高回声团块，与内膜关系密切。超声提示：宫内残留，请结合病史", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "左侧附件区可见一大小约60*50mm的囊性包块，内部可见脂液分层征。右侧附件区未见异常。超声提示：左侧卵巢畸胎瘤 D27.9", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "宫内妊娠，胎儿心率约168次/分，胎动可见。胎盘位于后壁，下缘距宫颈内口约25mm。超声提示：宫内中孕，胎盘低置状态 O44.0，建议随访。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "双侧卵巢显示不清，盆腔可见一大小约78*65mm的囊性包块，壁薄，内部可见多个分隔。超声提示：盆腔囊性包块，考虑卵巢来源可能，建议进一步检查。", "expected_organ_count": 1, "expected_diag_count": 1},

    # === 心脏超声 (46-60) ===
    {"text": "心脏各房室内径正常。室间隔及左室后壁厚度正常，运动协调。各瓣膜形态活动正常。CDFI未见异常血流信号。左心功能测定：EF约65%。超声提示：心脏结构及功能未见明显异常。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "左心房增大，前后径约42mm。左心室大小正常。二尖瓣回声增强，开放受限，瓣口面积约1.5平方厘米。CDFI示二尖瓣口可见高速射流。超声提示：风湿性心脏病，二尖瓣狭窄（中度） I05.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "左心室增大，舒张末内径约62mm，收缩末内径约48mm。室间隔及左室后壁厚度正常。左室壁运动弥漫性减弱。EF约35%。超声提示：扩张型心肌病 I42.0，左心功能减低。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "主动脉瓣回声增强钙化，瓣叶开放受限，瓣口面积约0.8平方厘米。瓣上流速约420cm/s。左心室肥厚，室间隔厚约14mm，左室后壁厚约13mm。超声提示：主动脉瓣狭窄（重度）伴左心室肥厚 I35.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "二尖瓣后叶于收缩期脱入左心房，脱垂深度约5mm。CDFI示收缩期二尖瓣口左房侧可见中度反流，反流面积约8平方厘米。超声提示：二尖瓣脱垂伴中度关闭不全 I34.1", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "室间隔肌部可见回声中断约6mm。CDFI示收缩期左向右分流信号。超声提示：先天性心脏病，室间隔缺损（肌部） Q21.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右心房室增大，肺动脉主干增宽约32mm。三尖瓣中量反流，估测肺动脉收缩压约55mmHg。超声提示：肺动脉高压（中度） I27.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "左心室壁节段性运动异常，前壁、前间隔中下段运动减弱。左心室舒张末内径约56mm。EF约45%。超声提示：冠心病，左心室前壁节段性运动异常 I25.1", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "心包腔内可见无回声区，右室前壁前方深约8mm，左室后壁后方深约12mm。心脏各房室内径正常。超声提示：心包积液（中量） I31.3", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "主动脉根部内径约48mm，升主动脉内径约45mm。主动脉瓣为三叶式，未见反流。超声提示：升主动脉增宽 I71.9，建议随访。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "左心房内可见一大小约35*28mm的团块状回声，附着于房间隔，活动度较大。超声提示：左心房占位，考虑粘液瘤可能 D15.1", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "三尖瓣前叶收缩期部分脱入右心房，CDFI示三尖瓣重度反流。右心房室增大。超声提示：三尖瓣脱垂伴重度关闭不全 I07.1", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "主动脉窦部呈瘤样扩张，内径约52mm。主动脉瓣为三叶式，轻微反流。超声提示：主动脉窦瘤 I71.9，建议外科评估。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "房间隔中部可见回声中断约15mm。CDFI示舒张晚期及收缩早期左向右分流。右心房室增大。超声提示：先天性心脏病，房间隔缺损（中央型） Q21.1", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "左室壁明显增厚，室间隔厚约22mm，左室后壁厚约18mm。左室流出道流速增快约280cm/s。SAM征阳性。超声提示：肥厚型心肌病（梗阻性） I42.1", "expected_organ_count": 1, "expected_diag_count": 1},

    # === 小器官/血管/其他 (61-80) ===
    {"text": "甲状腺左叶大小约48*16*14mm，右叶大小约50*18*16mm，峡部厚约3mm。实质回声均匀，未见明确结节。CDFI示血供分布正常。超声提示：甲状腺未见明显异常。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "甲状腺右叶中部可见一大小约8*6mm的低回声结节，边界清晰，形态规则，内部回声均匀。TI-RADS 3类。超声提示：甲状腺右叶结节，TI-RADS 3类，考虑良性。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "甲状腺左叶可见一大小约15*12mm的极低回声结节，边界模糊，形态不规则，内部可见微钙化。TI-RADS 4b类。超声提示：甲状腺左叶结节，TI-RADS 4b类，建议超声引导下穿刺活检。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "双侧乳腺腺体结构清晰，未见明确肿块。右侧乳腺外上象限可见一大小约6*5mm的无回声囊性结构，边界清晰。BI-RADS 2类。超声提示：双侧乳腺增生，右乳小囊肿。", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "左侧乳腺内上象限可见一大小约18*14mm的低回声结节，边界欠清晰，形态略不规则，内部回声不均匀。BI-RADS 4a类。超声提示：左乳结节，BI-RADS 4a类，建议穿刺活检。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右侧颈部可见多个低回声淋巴结，大者约18*8mm，皮髓质分界尚清晰。超声提示：右颈部淋巴结可见", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右颈总动脉分叉处可见一大小约13*10mm的不均质回声团块，CDFI示其内及周边血流信号丰富。超声提示：颈动脉体瘤可能 D44.6", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "双侧睾丸大小形态正常，实质回声均匀。左侧附睾头部可见一大小约8mm的无回声区，边界清晰。超声提示：左侧附睾囊肿", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "双侧腋窝可见多个低回声淋巴结，大者约22*12mm，皮髓质分界欠清晰。超声提示：双侧腋窝多发淋巴结肿大 R59.9", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "甲状腺弥漫性增大，回声减低不均匀，可见多个条索状高回声分隔，呈网格状改变。CDFI示血供极度丰富，呈火海征。超声提示：甲状腺功能亢进超声改变 Graves病 E05.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "双侧颌下腺大小形态正常，回声均匀。右侧腮腺内可见一大小约15*12mm的低回声结节，边界清晰，内部回声均匀。超声提示：右侧腮腺结节，考虑良性。", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "甲状旁腺区未见明确异常回声。甲状腺右叶后下方可见一大小约10*8mm的低回声区，边界清晰。超声提示：右甲状旁腺区低回声，考虑甲状旁腺腺瘤可能 E21.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右侧腹股沟区可见一大小约35*25mm的混合回声团块，与腹腔相通，可见肠管蠕动。超声提示：右侧腹股沟疝 K40.9", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右侧乳腺乳晕区可见一大小约12*10mm的低回声结节，边界清晰，形态规则，内部回声均匀。BI-RADS 3类。超声提示：右乳结节，BI-RADS 3类，考虑纤维腺瘤可能。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "颈总动脉内膜中层厚度约1.2mm。双侧颈总动脉分叉处可见多个大小不等的混合回声斑块，大者位于右侧约15*4mm。CDFI示管腔内血流通畅。超声提示：双侧颈动脉粥样硬化伴斑块形成 I70.0", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右侧睾丸体积增大，实质内可见一大小约22*18mm的低回声肿块，边界清晰，内部回声不均匀。CDFI示肿块内血供丰富。左侧睾丸大小形态正常。超声提示：右侧睾丸肿瘤，考虑精原细胞瘤可能 C62.9", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "颏下区可见一大小约30*25mm的无回声区，壁薄，内部透声好，与舌骨关系密切。超声提示：甲状舌管囊肿 Q89.2", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右侧腮腺弥漫性增大，回声不均匀减低，可见多个小片状低回声区。CDFI示血供增多。超声提示：右侧腮腺炎 K11.2", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "双侧乳腺呈退化萎缩改变，腺体层变薄，以脂肪组织为主。未见明确占位性病变。超声提示：双侧乳腺退行性改变，符合老年性乳腺改变。", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "甲状腺左叶上极可见一大小约6*5mm的微小结节，呈等回声，边界清晰。TI-RADS 2类。超声提示：甲状腺左叶微小良性结节。", "expected_organ_count": 1, "expected_diag_count": 1},

    # === 混合/复杂/边缘病例 (81-100) ===
    {"text": "肝脏右叶多发囊性病变，大者约50mm，左叶增大。胆囊显示不清。胰腺回声增强。脾大。双肾多发囊肿。超声提示：1、多囊肝 Q44.6 2、多囊肾 Q61.2 3、脾大。", "expected_organ_count": 6, "expected_diag_count": 3},
    {"text": "胆囊区未见正常胆囊结构，可见一大小约25*18mm的弧形强回声带，后伴宽大声影。超声提示：胆囊结石伴萎缩性胆囊炎，充满型结石 K80.1", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "肝脏缩小，表面结节状，回声弥漫性增强不均匀，门静脉内径约14mm。脾脏肋间厚约60mm。腹腔可见游离无回声区。超声提示：1、肝硬化伴门脉高压 K74.6 2、脾大 3、腹水 R18", "expected_organ_count": 3, "expected_diag_count": 3},
    {"text": "门静脉主干内径约15mm，其内可见低回声充盈缺损，范围约32*18mm，CDFI示缺损区无血流信号。超声提示：门静脉血栓形成 I81", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "右肾中部可见一大小约42*38mm的不均质回声肿块，内部可见不规则无回声区及钙化灶。CDFI示肿块内及周边丰富血流。超声提示：右肾占位性病变，考虑肾细胞癌可能 C64", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "胰腺体尾部可见一大小约28*25mm的囊性病变，内部可见分隔及附壁结节。胰管未见扩张。超声提示：胰腺囊性肿瘤，性质待定，建议MRI及EUS检查。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "腹主动脉局限性扩张，最大内径约42mm，长度约65mm，管壁可见粥样硬化斑块。超声提示：腹主动脉瘤 I71.4", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "双肾体积增大，实质回声增强，皮髓质分界不清。集合系统无分离。超声提示：双肾实质弥漫性病变，符合慢性肾病超声改变 N18.9", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "膀胱充盈欠佳，腔内可见一大小约20*15mm的不规则中高回声团，不随体位改变移动，基底宽。CDFI示基底可见血流信号。超声提示：膀胱占位性病变，考虑膀胱肿瘤 C67.9", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "肝内可见多个大小不等的强回声团，大者约35*30mm，后伴声影，沿胆管走行分布。肝内胆管扩张。超声提示：肝内胆管多发结石 K80.3", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "脾脏下极包膜下可见大小约35*30mm的低回声区，边界清晰。腹腔未见游离液体。超声提示：脾脏包膜下血肿，请结合外伤史。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "阑尾区可见一长约52mm、直径约12mm的管状低回声，壁厚约3mm，管腔内可见强回声粪石约6mm。周围可见少量渗出。超声提示：急性阑尾炎伴粪石 K35.9", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "患者口述：做了个B超，肝有点大，回声不太好。医生说右肝有个东西，大概两公分，看着不像好东西。胆囊还行。胰脏和脾都说没事。还说我肚子里有水。结论可能是肝癌，让我赶紧去查。", "expected_organ_count": 5, "expected_diag_count": 2},  # 肝硬化+肝癌可能+腹水
    {"text": "右上腹痛来做检查。肝脏右叶看到一个小光团，大概1.5厘米乘1厘米这样，边界还蛮清楚的，回声低。考虑肝血管瘤可能。胆结石术后复查。提示：肝血管瘤，胆结石术后改变，建议半年后复查B超。", "expected_organ_count": 2, "expected_diag_count": 2},
    {"text": "单位体检。B超医生说肝脏回声粗，考虑有轻度脂肪肝。胆囊壁上有个小息肉样突起，3毫米，不用处理。其他都正常。超声提示：1、轻度脂肪肝 2、胆囊息肉样病变（3mm），建议随访", "expected_organ_count": 2, "expected_diag_count": 2},
    {"text": "孕18周来做例行检查。胎儿发育正常，头围160，腹围145，股骨长27。胎盘位置前壁，厚22毫米。羊水正常。提示：中期妊娠，胎儿发育符合孕18周，目前未见明显异常。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "乳腺自检发现右乳有个硬块，不痛不痒。B超看到右乳外上象限有个结节，1.8乘1.5厘米，边界不清，形态不太规则，内部回声不均匀。BI-RADS分类4类，建议做穿刺。超声提示：右乳实性占位，BI-RADS 4类，建议穿刺活检。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "肾脏结石复查。右肾中盏可见一个强回声光团约6*4毫米，后方有声影。左肾正常，没有积水。超声提示：右肾结石（较小），建议多饮水。", "expected_organ_count": 2, "expected_diag_count": 1},
    {"text": "心悸胸闷来查心脏彩超。左房偏大38毫米，室间隔厚度约11毫米，二尖瓣轻度反流，EF值约58%。主动脉瓣三叶，活动尚可。提示：左房增大，二尖瓣轻度反流，建议定期随访。", "expected_organ_count": 1, "expected_diag_count": 1},
    {"text": "老年男性体检。前列腺增大明显，大小约52*45*42毫米，突入膀胱约15毫米，回声欠均匀，内可见多个强回声钙化斑。残余尿量约80毫升。超声提示：1、前列腺增生伴钙化 N40 2、膀胱残余尿量增多 R33", "expected_organ_count": 2, "expected_diag_count": 2},
]


def validate_report(report: dict, tc: dict) -> dict:
    """验证单份报告的结构化质量"""
    issues = []
    score = 100

    # 检查必需顶层字段
    for key in ["patient_info", "exam_info", "findings", "impression"]:
        if key not in report:
            issues.append(f"缺失字段: {key}")
            score -= 20

    # 检查 findings
    findings = report.get("findings", [])
    if not findings:
        issues.append("findings为空")
        score -= 15
    else:
        # 脏器数量合理性
        if len(findings) < tc.get("expected_organ_count", 1) * 0.5:
            issues.append(f"发现脏器数过少: {len(findings)} (期望≥{tc['expected_organ_count']})")
            score -= 10
        for f in findings:
            if not f.get("organ"):
                issues.append("finding缺少organ字段")
                score -= 5

    # 检查 impression
    impressions = report.get("impression", [])
    if not impressions:
        issues.append("impression为空")
        score -= 15
    else:
        if len(impressions) < tc.get("expected_diag_count", 1) * 0.5:
            issues.append(f"诊断数偏少: {len(impressions)} (期望≥{tc['expected_diag_count']})")
            score -= 10
        for imp in impressions:
            if not imp.get("diagnosis"):
                issues.append("impression缺少diagnosis字段")
                score -= 5

    # 检查幻觉：report中不应有不在范围内的 random 文字
    for f in findings:
        organ = f.get("organ", "")
        valid_organs = {"肝脏", "胆囊", "胆总管", "胰腺", "脾脏", "左肾", "右肾", "膀胱", "前列腺", "子宫", "卵巢", "腹腔",
                        "心脏", "甲状腺", "乳腺", "颈动脉", "睾丸", "附睾", "腮腺", "阑尾", "腹主动脉", "门静脉",
                        "胎儿", "宫颈", "输卵管", "淋巴结", "甲状旁腺", "颌下腺", "双侧附件", "附件", "盆腔"}
        # 宽松检查：organ not empty and not gibberish
        if organ and len(organ) > 20:
            issues.append(f"脏器名称异常: {organ[:30]}")
            score -= 5

    return {"score": max(0, score), "issues": issues}


def main():
    print("=" * 70)
    print("超声报告结构化 — 100条批量测试")
    print(f"API: {API}")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = []
    total_start = time.time()

    for i, tc in enumerate(TEST_CASES):
        case_start = time.time()
        try:
            resp = httpx.post(API, json={"text": tc["text"]}, timeout=90)
            elapsed = time.time() - case_start

            if resp.is_success:
                data = resp.json()
                report = data.get("report", {})
                validation = validate_report(report, tc)

                findings_count = len(report.get("findings", []))
                diags_count = len(report.get("impression", []))
                diags = [imp.get("diagnosis", "") for imp in report.get("impression", [])]
                icd10s = [imp.get("icd10") for imp in report.get("impression", []) if imp.get("icd10")]

                results.append({
                    "index": i + 1,
                    "success": True,
                    "elapsed": elapsed,
                    "score": validation["score"],
                    "findings_count": findings_count,
                    "diags_count": diags_count,
                    "icd10_count": len(icd10s),
                    "issues": validation["issues"],
                })

                print(f"[{i+1:3d}] OK  score={validation['score']:3d}  "
                      f"findings={findings_count}  diags={diags_count}  "
                      f"ICD10={len(icd10s)}  {elapsed:.1f}s")
                if diags:
                    print(f"       诊断: {' / '.join(diags[:3])}")

            else:
                results.append({
                    "index": i + 1,
                    "success": False,
                    "elapsed": elapsed,
                    "error": resp.text[:200],
                })
                print(f"[{i+1:3d}] FAIL  HTTP {resp.status_code}  {resp.text[:100]}")

        except Exception as e:
            elapsed = time.time() - case_start
            results.append({
                "index": i + 1,
                "success": False,
                "elapsed": elapsed,
                "error": str(e),
            })
            print(f"[{i+1:3d}] FAIL  {type(e).__name__}: {str(e)[:100]}")

    total_elapsed = time.time() - total_start

    # ==================== 统计 ====================
    success_results = [r for r in results if r["success"]]
    fail_results = [r for r in results if not r["success"]]

    print("\n" + "=" * 70)
    print("                            测 试 汇 总")
    print("=" * 70)

    print(f"\n  总用例数:      {len(TEST_CASES)}")
    print(f"  成功:          {len(success_results)} ({len(success_results)/len(TEST_CASES)*100:.1f}%)")
    print(f"  失败:          {len(fail_results)} ({len(fail_results)/len(TEST_CASES)*100:.1f}%)")

    if success_results:
        scores = [r["score"] for r in success_results]
        avg_score = statistics.mean(scores)
        median_score = statistics.median(scores)
        min_score = min(scores)
        max_score = max(scores)

        times = [r["elapsed"] for r in success_results]
        avg_time = statistics.mean(times)
        median_time = statistics.median(times)
        p95_time = sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0]

        f_counts = [r["findings_count"] for r in success_results]
        d_counts = [r["diags_count"] for r in success_results]
        icd10_counts = [r["icd10_count"] for r in success_results]

        print(f"\n  --- 评分 ---")
        print(f"  平均分:        {avg_score:.1f}")
        print(f"  中位分:        {median_score}")
        print(f"  最低分:        {min_score}")
        print(f"  最高分:        {max_score}")

        print(f"\n  --- 发现与诊断 ---")
        print(f"  平均脏器和发现数:  {statistics.mean(f_counts):.1f} (范围 {min(f_counts)}-{max(f_counts)})")
        print(f"  平均诊断数:        {statistics.mean(d_counts):.1f} (范围 {min(d_counts)}-{max(d_counts)})")
        total_icd10 = sum(icd10_counts)
        print(f"  ICD-10编码覆盖率:  {total_icd10}/{sum(d_counts)} ({total_icd10/sum(d_counts)*100:.1f}%)" if sum(d_counts) > 0 else "  ICD-10编码覆盖率: N/A")

        print(f"\n  --- 性能 ---")
        print(f"  总耗时:        {total_elapsed:.1f}s")
        print(f"  平均延迟:      {avg_time:.1f}s")
        print(f"  中位延迟:      {median_time:.1f}s")
        print(f"  P95延迟:       {p95_time:.1f}s")
        print(f"  吞吐量:        {len(success_results)/total_elapsed:.2f} req/s")

        # 分数分布
        score_bins = {"100": 0, "95-99": 0, "80-94": 0, "60-79": 0, "<60": 0}
        for s in scores:
            if s == 100:
                score_bins["100"] += 1
            elif s >= 95:
                score_bins["95-99"] += 1
            elif s >= 80:
                score_bins["80-94"] += 1
            elif s >= 60:
                score_bins["60-79"] += 1
            else:
                score_bins["<60"] += 1

        print(f"\n  --- 评分分布 ---")
        for bin_name, count in score_bins.items():
            bar = "█" * (count // 2) if count > 0 else ""
            print(f"  {bin_name:>6}: {count:3d} ({count/len(success_results)*100:4.1f}%) {bar}")

        # 常见问题
        all_issues = []
        for r in success_results:
            all_issues.extend(r["issues"])
        if all_issues:
            from collections import Counter
            issue_counts = Counter(all_issues)
            print(f"\n  --- 常见问题 (Top 10) ---")
            for issue, count in issue_counts.most_common(10):
                print(f"  [{count:2d}x] {issue}")

    if fail_results:
        print(f"\n  --- 失败详情 ---")
        for r in fail_results:
            print(f"  [{r['index']:3d}] {r.get('error', 'unknown')[:150]}")

    print("\n" + "=" * 70)

    # 保存详细结果
    output_path = Path(__file__).parent / "test_results_100.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": len(TEST_CASES),
                "success": len(success_results),
                "failed": len(fail_results),
                "avg_score": avg_score if success_results else 0,
                "avg_latency_s": avg_time if success_results else 0,
                "total_time_s": total_elapsed,
                "icd10_coverage_rate": f"{total_icd10/sum(d_counts)*100:.1f}%" if sum(d_counts) > 0 else "N/A",
            },
            "details": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存: {output_path}")


if __name__ == "__main__":
    main()
