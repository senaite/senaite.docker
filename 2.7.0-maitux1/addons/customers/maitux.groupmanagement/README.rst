maitux.groupmanagement
======================

独立组管理 Add-on for SENAITE。

功能
----

- 把"组设置"从 ``@@usergroup-groupprefs``（与用户共用的控制面板）
  独立成单独的组管理界面
- 在 ``@@lims-setup`` 上新增带图标的入口（FontAwesome ``fa-users-cog``）
- 组界面中**取消 Manager 角色**的分配（界面与后端双重拦截）
- 组界面中**取消删除组**的功能（界面无 Remove 列，后端拦截
  ``delete:list``）
- 保留：新建组、组属性编辑、组成员管理（含移出成员）

独立视图
--------

- ``@@maitux-group-management`` —— 组总览（搜索、角色矩阵保存）
- ``@@maitux-group-details`` —— 组属性 / 新建组
- ``@@maitux-group-membership`` —— 组成员管理

旧入口（``@@usergroup-userprefs`` / ``@@usergroup-groupprefs``）保持不动。

卸载行为
--------

卸载 add-on 后：

- ``@@lims-setup`` 上的"组管理"入口立即消失
  （卸载处理器清除安装标记；即使浏览器层残留也不显示）
- 独立组管理页面（``@@maitux-group-management`` 等）不再可访问
  （卸载处理器尽力从 ``portal_skins`` 移除浏览器层）

注意：升级本 add-on 代码后，若入口未出现，请在 Add-ons 面板
先卸载再安装一次（安装处理器负责写入安装标记）。

安装
----

1. 将 ``maitux.groupmanagement`` 加入 buildout：

   .. code-block:: ini

      [buildout]
      develop +=
          src/maitux.groupmanagement
      eggs +=
          maitux.groupmanagement

      [instance]
      zcml +=
          maitux.groupmanagement

2. 运行 ``bin/buildout`` 并重启实例
3. 在 Site Setup -> Add-ons 中安装 ``Maitux Group Management``

Docker 部署（2.7.0-maitux1 镜像）
--------------------------------

1. 将本 add-on 目录复制到镜像构建上下文的客户 add-on 目录：

   .. code-block:: sh

      cp -r src/maitux.groupmanagement \
            <docker>/senaite.docker/2.7.0-maitux1/addons/customers/maitux.groupmanagement

2. 在 ``addons/customers/custom-addon.cfg`` 中追加（共四处）：

   .. code-block:: ini

      [buildout]
      develop +=
          /opt/addons/customers/maitux.groupmanagement
      eggs +=
          maitux.groupmanagement

      [instance]
      zcml +=
          maitux.groupmanagement

      [plonesite]
      profiles +=
          maitux.groupmanagement:default

3. 重新构建镜像并启动容器，Add-ons 面板会出现
   ``Maitux Group Management``，安装后生效。

测试
----

.. code-block:: sh

   python src/maitux.groupmanagement/src/maitux/groupmanagement/tests/test_groupmanagement.py

测试不依赖 Plone 运行时（轻量 stub），Python 2.7 / 3.x 均可运行。
