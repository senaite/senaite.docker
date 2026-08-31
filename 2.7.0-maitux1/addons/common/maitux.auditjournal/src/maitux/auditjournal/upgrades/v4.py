# -*- coding: utf-8 -*-
"""profile v3 -> v4：修复 v3 引入的故障。

v3 往 user 分类加的那条 action 用了**中文 title + i18n:domain**，
导致 CMFCore 用 Message() 包字节串时 UnicodeDecodeError，
而 personal bar 每页都渲染 —— 整站多数页面打不开。

本 step 重新导入 actions（现在是纯 ASCII 标题），把那条坏 action 覆盖掉。
若站点里那条已被手工删除，重新导入会把它建回来，结果一致。
"""

import logging

logger = logging.getLogger("maitux.auditjournal")

PROFILE = "profile-maitux.auditjournal:default"


def upgrade(setup_tool):
    logger.warning("auditjournal: upgrade v3 -> v4, re-importing actions "
                   "(ASCII title; v3 shipped a non-ASCII one that broke "
                   "the personal bar)")
    setup_tool.runImportStepFromProfile(PROFILE, "actions")
    logger.warning("auditjournal: upgrade v3 -> v4 finished")
