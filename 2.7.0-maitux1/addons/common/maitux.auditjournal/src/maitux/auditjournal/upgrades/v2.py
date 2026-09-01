# -*- coding: utf-8 -*-
"""GenericSetup upgrade step：profile 版本 1 -> 2。

★ R4b 的对价：本包豁免了卸载能力，就**只剩升级这一条路**。所以这个 step
  即使没有实际的 profile 变更也必须存在并被执行验证过一次 —— 否则等到真要改
  profile 的那天，才发现升级通道从没通过。

★ 这里**不做表结构迁移**。表迁移在 `db.ensure_schema()` 按 DSN 惰性补齐：
  GS 的 upgrade step 是**站点级**的，多库形态下在客户 A 的站点上执行只会
  升到客户 A 的库，别的库不动（实施方案 §8.4）。两者职责必须分开：

      GS upgrade step  →  profile 侧（rolemap / registry / 类型定义…）
      ensure_schema    →  PostgreSQL 表结构，按 DSN，与站点无关
"""

import logging

logger = logging.getLogger("maitux.auditjournal")

PROFILE = "profile-maitux.auditjournal:default"


def upgrade(setup_tool):
    """v1 -> v2：本版没有 profile 侧变更，只重跑 rolemap 并留痕。

    重跑 rolemap 是幂等的，顺带修掉「站点装了 v1 之后手工改过权限」的情况。
    """
    logger.warning("auditjournal: running upgrade step v1 -> v2 on %r",
                   setup_tool)
    setup_tool.runImportStepFromProfile(PROFILE, "rolemap")
    logger.warning("auditjournal: upgrade step v1 -> v2 finished "
                   "(profile side only; table schema is handled lazily "
                   "per DSN by db.ensure_schema)")
