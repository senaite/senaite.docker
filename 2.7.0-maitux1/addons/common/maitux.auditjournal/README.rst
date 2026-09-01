maitux.auditjournal
===================

**本包不提供卸载能力（R4b 合规豁免，首例）。** 审计追踪在 GMP / 21 CFR Part 11
下不允许被用户关闭；而且 GenericSetup profile 卸不掉一张 PostgreSQL 表，
给一个卸不干净的"卸载"按钮比没有按钮更危险 —— 它让人以为卸干净了。

停用的正确做法
--------------

不要试图卸载。确需停止记录时：

1. 把 ``maitux.auditjournal`` 从 ``common-addons.cfg`` 的三段里移除并重建镜像；
2. **表和数据保留不动** —— 它是审计证据，删除本身就是合规事故。

包外状态
--------

本包在 ZODB 之外持有状态：PostgreSQL 表 ``audit_journal``，落在**该对象所属
ZODB 的那个库**里（单库形态 = ``lims_db``；一客户一库形态 = 各客户自己的库）。

- 建表与迁移是**惰性且幂等**的：进程内首次对某个 DSN 使用时执行
  ``CREATE TABLE/INDEX IF NOT EXISTS``，并比对表注释里的 schema 版本。
- **不挂在站点级 upgrade step 上** —— 那在多库形态下升不全。

升级（豁免卸载换来的义务）
--------------------------

放弃卸载 = 放弃唯一的兜底逃生口，此后只剩升级一条路。所以 profile 的任何
后续变更只能走 upgrade step，不得依赖"重装一次就好了"。

.. warning::

   ``upgrades/`` 目录目前是占位，真正的 upgrade step 在 Backlog **S10** 落地。
   在 S10 完成之前，本包**尚未**履行 R4b 的对价义务，不得对外宣称合规就绪。

安装与生效
----------

本包在 ``addons/common/``，属于**构建期 COPY**：改了必须重建镜像，重启不生效。
记录层不依赖 GenericSetup profile —— 镜像起来就开始记；profile 只做一件事：
把 ``maitux.auditjournal.ViewAuditJournal`` 授给 Manager / LabManager。

文档
----

- 为什么这么做：``Docs/auditlog-journal-实施方案.md``
- 怎么实现：``Docs/auditlog-journal-技术设计.md``
- 怎么切片：``Docs/auditlog-journal-Backlog.md``
- 怎么运维：``Docs/auditlog-journal-Runbook.md``
