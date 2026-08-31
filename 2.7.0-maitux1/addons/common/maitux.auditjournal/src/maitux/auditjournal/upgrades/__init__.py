# -*- coding: utf-8 -*-
"""profile 侧的升级步骤。

★ 目前是占位：真正的 upgrade step 在 Backlog S10 落地。
R4b 的对价是"豁免卸载就必须从第一版把升级路径建起来并验证过一次"，
在 S10 之前本包**尚未**履行这条义务 —— 见 README.rst 的 warning。

★ 注意：**表结构迁移不走这里**。GenericSetup upgrade step 是站点级的，
多库形态下只会升到当前站点所在的库。schema 迁移在 db.ensure_schema()，
按 DSN 惰性比对（实施方案 §8.4）。
"""
