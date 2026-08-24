# -*- coding: utf-8 -*-
"""模块配置常量"""

# 项目标识（用于日志和配置查找）
PROJECTNAME = "maitux.groupmanagement"

# 安装标记（portal property）：安装时写入、卸载时清除，
# 用于在浏览器层尚未移除时也保证 @@lims-setup 入口不显示
INSTALLED_PROPERTY = "maitux_groupmanagement_installed"

# 浏览器层名称（profiles/default/browserlayer.xml 中的 name）
BROWSER_LAYER_NAME = "maitux.groupmanagement"
