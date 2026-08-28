# -*- coding: utf-8 -*-
"""第一阶段静态目标位定义 —— 代码写死的唯一来源

本模块是第一阶段"代码里写死静态数据"的唯一来源：

- 采集界面直接读取本模块生成"待分配目标列表"
- 回写服务只允许回写这里定义的目标位
- `manage_results` 只读渲染同样依赖这里的关键字集合

第一阶段目标位采用 `target_key` 字符串抽象，不直接引用 Analysis UID；
第二阶段再升级为独立的 InstrumentReading content type 与 UID 引用
（`assigned_analysis_uids`）。
"""

# 入站接口固定鉴权 Token（第一阶段写死，后续升级为配置界面）
PHASE1_INGEST_TOKEN = "maitux-phase1-instrument-acquisition-token"

# 远端采集端模式（默认开启）：
#   True  —— 云 LIMS 与实验室本地采集端（agent）分离部署。LIMS 点「开始采集」
#            只标记会话为监听状态并登记占用者，**不**由 LIMS 进程内 relay 直连
#            仪器（云连不到实验室内网）；本地采集端轮询
#            `@@instrument_acquisition_api_agent_config` 拿到 start/ip/port 后
#            自行连接仪器，读数按 instrument_code 推回 LIMS。
#   False —— 进程内 relay 模式（LIMS 与仪器同网，或仪器地址可直连时）：
#            LIMS 自己连接仪器收数，读数进 relay 内存队列由采集页轮询写入。
PHASE1_AGENT_MODE = True

# 开始采集时仪器 TCP 连通性探测超时（秒）
PHASE1_TCP_PROBE_TIMEOUT = 3

# Worksheet annotations 存储键
PHASE1_ANNOTATION_KEY = "maitux.instrument_acquisition.v1.session"
PHASE1_SESSION_INDEX_KEY = "maitux.instrument_acquisition.v1.session_index"

# 第一阶段写死的分析字段关键字（Interim Field keyword）
T_NAME_KEYWORD = "T_name"
T_WEIGHT_KEYWORD = "T_weight"

PHASE1_KEYWORDS = (T_NAME_KEYWORD, T_WEIGHT_KEYWORD)

# 目标位定义：interim_keyword 层级的元数据
PHASE1_TARGET_DEFINITIONS = [
    {
        # 抽象目标位标识（= interim keyword，页面按分析行组合出具体 target_key）
        "target_key": T_NAME_KEYWORD,
        # 空 = 不限定 Analysis Service，作用于 Worksheet 内所有含该 interim 的分析行
        "analysis_service_keyword": "",
        "interim_keyword": T_NAME_KEYWORD,
        "display_title": u"名称",
        "allow_multi_assign": False,
        "sort_order": 1,
        "value_type": "string",
    },
    {
        "target_key": T_WEIGHT_KEYWORD,
        "analysis_service_keyword": "",
        "interim_keyword": T_WEIGHT_KEYWORD,
        "display_title": u"重量",
        "allow_multi_assign": True,
        "sort_order": 2,
        "value_type": "float",
    },
]

# target_key 分隔符："{analysis_uid}:{interim_keyword}" 或
# "{analysis_uid}:{interim_keyword}:{seq}"（数组字段的手动添加行）
TARGET_KEY_SEPARATOR = ":"

# 数组类型 result_type（interim field）：值存 JSON 数组，目标位支持手动添加行
ARRAY_RESULT_TYPES = (
    "list",
    "multiselect",
    "multiselect_duplicates",
    "multichoice",
)


def is_array_result_type(result_type):
    """interim 的 result_type 是否数组类型"""
    return ((result_type or u"").strip().lower()
            in ARRAY_RESULT_TYPES)


def get_target_definitions():
    """返回目标位定义的副本列表"""
    return [dict(item) for item in PHASE1_TARGET_DEFINITIONS]


def get_target_definition(target_key):
    """按关键字（interim keyword）返回目标位定义，找不到返回 None"""
    for item in PHASE1_TARGET_DEFINITIONS:
        if item["target_key"] == target_key:
            return dict(item)
    return None


def get_readonly_keywords():
    """返回第一阶段只读保护的关键字集合（供 manage_results 使用）"""
    return list(PHASE1_KEYWORDS)


def make_target_key(analysis_uid, keyword, seq=None):
    """由分析 UID 与 interim keyword 组合出具体目标位的 target_key

    数组字段（result_type 为 list/multiselect 等）支持手动添加行：
    - 基础行（seq=None/0）："{analysis_uid}:{keyword}"
    - 添加行（seq>=1）："{analysis_uid}:{keyword}:{seq}"

    第一阶段用 target_key 字符串抽象"某个分析行的某个字段"；
    第二阶段迁移到 `assigned_analysis_uids` 时，只需解析此字符串即可。
    """
    key = u"{}{}{}".format(analysis_uid, TARGET_KEY_SEPARATOR, keyword)
    if seq:
        key = u"{}{}{}".format(key, TARGET_KEY_SEPARATOR, seq)
    return key


def parse_target_key_full(target_key):
    """解析 target_key，返回 (analysis_uid, interim_keyword, seq)

    - "{analysis_uid}:{keyword}"          → (uid, kw, 0)
    - "{analysis_uid}:{keyword}:{seq}"    → (uid, kw, seq)
    无法解析时返回 (None, None, None)。
    """
    target_key = target_key or u""
    parts = target_key.split(TARGET_KEY_SEPARATOR)
    if len(parts) < 2:
        return None, None, None
    analysis_uid = (parts[0] or u"").strip()
    keyword = (parts[1] or u"").strip()
    if not analysis_uid or not keyword:
        return None, None, None
    seq = 0
    if len(parts) > 2:
        try:
            seq = int(parts[2])
        except (TypeError, ValueError):
            return None, None, None
    return analysis_uid, keyword, seq


def parse_target_key(target_key):
    """解析 target_key，返回 (analysis_uid, interim_keyword)

    兼容数组字段的带序号 target_key（"{uid}:{kw}:{seq}"），
    只返回前两段。无法解析时返回 (None, None)。
    """
    analysis_uid, keyword, _seq = parse_target_key_full(target_key)
    return analysis_uid, keyword
