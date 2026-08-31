# -*- coding: utf-8 -*-
"""maitux.auditjournal —— SENAITE 快照元数据的 PostgreSQL 索引。

权威审计记录仍是 ZODB annotation，本表只是索引（实施方案 §1）。
"""

import logging

logger = logging.getLogger("maitux.auditjournal")
