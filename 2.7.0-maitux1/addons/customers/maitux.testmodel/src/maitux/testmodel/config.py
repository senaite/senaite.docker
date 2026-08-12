# -*- coding: utf-8 -*-
"""模块配置常量"""

# 导入 CMF 核心权限
from Products.CMFCore.permissions import AddPortalContent

# 项目标识（用于日志和配置查找）
PROJECTNAME = "maitux.testmodel"

# 内容类型 -> 新建权限映射
ADD_CONTENT_PERMISSIONS = {
    # 在此处添加模块专属的权限映射
    # 'YourType': AddPortalContent,
}
