# -*- coding: utf-8 -*-
from maitux.roles import _

PROJECTNAME = "maitux.roles"
PROFILE_ID = "profile-%s:default" % PROJECTNAME

# 统一初始密码（与容器环境 PASSWORD 保持一致）
DEFAULT_PASSWORD = "Maitux=123456"

# 基础权限：所有业务管理类角色共享的 LabManager 级别子集
BASE_PERMISSIONS = [
    "View",
    "Access contents information",
    "Add portal content",
    "Modify portal content",
    "senaite.core: View Navigation",
    "senaite.core: View Dashboard",
    "senaite.core: Manage Bika",
    "senaite.core: View Results",
]

# 角色定义
#   role_id       : Plone 角色 ID（= 组 ID，英文去空格）
#   title_msg     : 界面显示名（i18n Message，msgid 为英文全名）
#   username      : 登录账号（英文去空格，小写）
#   email         : 账号邮箱（占位，可后续修改）
#   permissions   : 该角色预设的权限（增量授予，不覆盖已有授权）
#   inherit_labmanager : 是否直接继承 LabManager 的全部权限
ROLE_DEFINITIONS = [
    {
        "role_id": "MethodAdministrator",
        "title_msg": _(u"Method Administrator", default=u"Method Administrator"),
        "username": "methodadministrator",
        "email": "methodadministrator@example.com",
        "permissions": BASE_PERMISSIONS + [
            "senaite.core: Add Method",
            "senaite.core: Manage Reference",
        ],
        "inherit_labmanager": False,
    },
    {
        "role_id": "InstrumentAdministrator",
        "title_msg": _(u"Instrument Administrator", default=u"Instrument Administrator"),
        "username": "instrumentadministrator",
        "email": "instrumentadministrator@example.com",
        "permissions": BASE_PERMISSIONS + [
            "senaite.core: Add Instrument",
            "senaite.core: Add InstrumentLocation",
            "senaite.core: Add InstrumentType",
            "senaite.core: Import Instrument Results",
        ],
        "inherit_labmanager": False,
    },
    {
        "role_id": "InventoryAdministrator",
        "title_msg": _(u"Inventory Administrator", default=u"Inventory Administrator"),
        "username": "inventoryadministrator",
        "email": "inventoryadministrator@example.com",
        "permissions": BASE_PERMISSIONS + [
            "senaite.core: Add StorageLocation",
            "senaite.core: Add Supplier",
        ],
        "inherit_labmanager": False,
    },
    {
        "role_id": "StabilityAdministrator",
        "title_msg": _(u"Stability Administrator", default=u"Stability Administrator"),
        "username": "stabilityadministrator",
        "email": "stabilityadministrator@example.com",
        "permissions": BASE_PERMISSIONS + [
            "maitux.stability: Add Stability Plan Template",
            "senaite.core: Add StorageLocation",
        ],
        "inherit_labmanager": False,
    },
    {
        "role_id": "StabilityInventoryAdministrator",
        "title_msg": _(u"Stability-Inventory Administrator",
                       default=u"Stability-Inventory Administrator"),
        "username": "stabilityinventoryadministrator",
        "email": "stabilityinventoryadministrator@example.com",
        "permissions": BASE_PERMISSIONS + [
            "maitux.stability: Add Stability Plan Template",
            "senaite.core: Add StorageLocation",
            "senaite.core: Add Supplier",
        ],
        "inherit_labmanager": False,
    },
    {
        "role_id": "BusinessSystemAdministrator",
        "title_msg": _(u"Business System Administrator",
                       default=u"Business System Administrator"),
        "username": "businesssystemadministrator",
        "email": "businesssystemadministrator@example.com",
        "permissions": BASE_PERMISSIONS + [
            "senaite.core: Manage Analysis Requests",
            "senaite.core: Manage Worksheets",
            "senaite.core: Manage Invoices",
            "senaite.core: Manage Reference",
        ],
        "inherit_labmanager": True,
    },
    {
        "role_id": "ITSystemEngineer",
        "title_msg": _(u"IT System Engineer", default=u"IT System Engineer"),
        "username": "itsystemengineer",
        "email": "itsystemengineer@example.com",
        "permissions": BASE_PERMISSIONS + [
            "Manage users",
            "Manage groups",
            "Manage portal",
            "senaite.core: Access JSON API",
            "senaite.core: Manage Login Details",
        ],
        "inherit_labmanager": False,
    },
]
