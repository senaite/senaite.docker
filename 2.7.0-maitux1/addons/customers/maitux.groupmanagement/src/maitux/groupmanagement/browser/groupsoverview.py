# -*- coding: utf-8 -*-
"""独立组管理总览视图

与 senaite.core 的 ``@@usergroup-groupprefs`` 相比：
  - 不显示 Manager 角色列 / 复选框（``portal_roles`` 排除 Manager）
  - 不提供删除组的 UI（模板无 Remove 列）
  - 后端兜底：即使伪造请求提交 ``delete:list`` 或 Manager 角色，
    也不会删除组或写入 Manager 角色

入口位于 ``@@lims-setup``（见 setupview.py）。
"""

from senaite.core import logger
from senaite.core.browser.usergroup.usergroups_groupsoverview import \
    GroupsOverviewControlPanel as BaseView

MANAGER_ROLE = "Manager"

# 组角色复选框字段名的前后缀（与模板中 name="group_<id>:list" 对应）
GROUP_FIELD_PREFIX = "group_"
GROUP_FIELD_SUFFIX = ":list"


class GroupManagementView(BaseView):
    """独立组管理总览（无 Manager 角色、无删除组）"""

    @property
    def portal_roles(self):
        """返回除 Manager 外的全部角色"""
        roles = super(GroupManagementView, self).portal_roles
        return [role for role in roles if role != MANAGER_ROLE]

    def deleteGroups(self, *args, **kw):
        """删除组在此 add-on 中禁用：记录并忽略

        即使基类在处理表单时发现删除参数（例如未来模板改动），
        这里也会拦截，保证任何路径都不会真正删除组。
        """
        logger.info(
            "Group deletion is disabled by maitux.groupmanagement: %s"
            % (args,))
        return True

    def __call__(self):
        """接管请求：清洗表单后再交给基类渲染/保存

        基类（CMFPlone GroupsOverviewControlPanel）收到
        ``form.button.Modify`` 时会保存角色并处理 ``delete:list``。
        这里在调用基类前：
          1. 移除 ``delete:list`` —— 基类永远不会删除组
          2. 从 ``group_<id>:list`` 中剔除 Manager —— 基类无法写入该角色
        角色保存仍由基类完成（幂等），行为与原界面一致。
        """
        form = self.request.form
        if "form.button.Modify" in form:
            self._strip_delete(form)
            self._strip_manager(form)
        return super(GroupManagementView, self).__call__()

    @staticmethod
    def _strip_delete(form):
        """移除删除组相关的所有请求参数"""
        for key in [k for k in list(form.keys())
                    if k == "delete:list" or k == "delete"]:
            del form[key]

    @staticmethod
    def _strip_manager(form):
        """从组角色字段中剔除 Manager，防御伪造请求"""
        for key in [k for k in list(form.keys())
                    if k.startswith(GROUP_FIELD_PREFIX)
                    and k.endswith(GROUP_FIELD_SUFFIX)]:
            value = form[key]
            if not isinstance(value, (list, tuple)):
                value = [value]
            form[key] = [role for role in value if role != MANAGER_ROLE]
