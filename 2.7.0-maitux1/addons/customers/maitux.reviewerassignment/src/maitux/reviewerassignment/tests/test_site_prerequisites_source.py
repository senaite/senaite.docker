# -*- coding: utf-8 -*-
"""站点前置条件自检的回归测试

审核人机制只覆盖「工作表内」的分析项 —— guard 拿不到工作表时一律放行。
真正把普通分析员挡在工作表之外的是 SENAITE 自己的 `AllowToSubmitNotAssigned=False`。
该设置一旦打开，不建工作表也能提交，本 addon 的约束整体失效。

自检只告警、不阻断：SENAITE 的设置归 SENAITE 管，本 addon 不去覆盖它。
"""

import io
import os
import unittest


SETUPHANDLERS = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "setuphandlers.py"))


def read_setuphandlers():
    """只返回代码行，剔除注释行（同 test_no_workflow_mutation_source）"""
    with io.open(SETUPHANDLERS, encoding="utf-8") as handle:
        lines = handle.readlines()
    return u"".join(
        line for line in lines if not line.lstrip().startswith(u"#"))


class TestSitePrerequisites(unittest.TestCase):
    """自检必须存在、被调用，且不改变站点设置"""

    def test_check_is_defined(self):
        """自检函数存在"""
        self.assertIn("def check_site_prerequisites", read_setuphandlers())

    def test_check_is_wired_into_install(self):
        """自检必须挂进安装编排，否则永远不会跑"""
        self.assertIn("check_site_prerequisites()", read_setuphandlers())

    def test_check_reads_the_right_setting(self):
        """读的是 AllowToSubmitNotAssigned"""
        self.assertIn("getAllowToSubmitNotAssigned", read_setuphandlers())

    def test_check_only_warns_never_writes(self):
        """只告警不阻断：不得改写站点设置，也不得抛异常中断安装"""
        source = read_setuphandlers()
        self.assertNotIn("setAllowToSubmitNotAssigned", source)
        # 自检段落里不得出现 raise
        block = source.split("def check_site_prerequisites", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertNotIn("raise", block)

    def test_check_warns_when_setting_is_enabled(self):
        """设置为开时必须走 logger.warn 分支"""
        source = read_setuphandlers()
        block = source.split("def check_site_prerequisites", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("if allow_not_assigned:", block)
        self.assertIn("logger.warn", block)

    def test_check_degrades_quietly_without_setup(self):
        """取不到 bika_setup 或读取失败时安静跳过，不能让安装失败"""
        source = read_setuphandlers()
        block = source.split("def check_site_prerequisites", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("if setup_tool is None:", block)
        self.assertIn("except Exception:", block)


if __name__ == "__main__":
    unittest.main()
