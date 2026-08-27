# -*- coding: utf-8 -*-

DEFAULT_CATEGORIES = u"""
GHS01|Explosive|爆炸物|ghs/GHS01.svg
GHS02|Flammable|易燃物|ghs/GHS02.svg
GHS03|Oxidizing|氧化性物质|ghs/GHS03.svg
GHS04|Compressed gas|高压压缩气体|ghs/GHS04.svg
GHS05|Corrosive|腐蚀性（酸 / 碱）|ghs/GHS05.svg
GHS06|Acute toxicity|剧毒 / 急性毒性|ghs/GHS06.svg
GHS07|Health hazard|有害 / 刺激性|ghs/GHS07.svg
GHS08|Serious health hazard|致癌 / 致畸 / 致突变|ghs/GHS08.svg
GHS09|Environmental hazard|环境危害|ghs/GHS09.svg
BIO01|Biohazard|传染性 / 生物危害|iso/W009.svg
RAD01|Radioactive|电离辐射|iso/W003.svg
NIR01|Non-ionising radiation|紫外 / 激光 / 射频 辐射|iso/W005.svg
MAG01|Magnetic field|强磁场（NMR / MRI）|iso/W006.svg
ELEC01|Electricity|触电危险|iso/W012.svg
HSURF01|Hot surface|高温表面（烫伤）|iso/W017.svg
HOT01|Hot content|高温内容物|iso/W079.svg
STEAM01|Hot steam|高温蒸汽 / 灭菌|iso/W080.svg
COLD01|Low temperature|低温 / 冷藏储存|iso/W010.svg
ASPH01|Asphyxiating atmosphere|窒息性 / 低温惰性气体|iso/W041.svg
""".strip()

LEGACY_HAZARD_EN_COMMON = {
    u"GHS01": u"explosive",
    u"GHS02": u"flammable",
    u"GHS03": u"oxidizing",
    u"GHS04": u"pressurised gas",
    u"GHS05": u"acid / caustic",
    u"GHS06": u"poisonous",
    u"GHS07": u"harmful / irritant",
    u"GHS08": u"carcinogenic / mutagenic",
    u"GHS09": u"environmentally hazardous",
    u"BIO01": u"infectious / biological",
    u"RAD01": u"ionising radiation",
    u"NIR01": u"UV / laser / RF",
    u"MAG01": u"NMR / MRI",
    u"ELEC01": u"electric shock",
    u"HSURF01": u"hot to touch",
    u"HOT01": u"heated material",
    u"STEAM01": u"autoclave / sterilisation",
    u"COLD01": u"freezing / cold storage",
    u"ASPH01": u"cryogenic / inert gas",
}

PROJECTNAME = "maitux.hazardcategories"
PROFILE_ID = "profile-%s:default" % PROJECTNAME
