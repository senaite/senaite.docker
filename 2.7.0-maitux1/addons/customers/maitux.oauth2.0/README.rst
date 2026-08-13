=============
maitux.oauth2
=============

竹云 (Bamboocloud) IDaaS 的 **OAuth 2.0 标准授权码模式** 统一登录插件，用于
SENAITE 2.7 / Plone 5.2 / Python 2.7。

与 ``senaite.oidc`` 的区别：那个插件依赖 ``ftw.oidcauth``，走的是 OIDC
(id_token / discovery / JWKS)。本插件只用纯 OAuth 2.0 接口，不需要 id_token，
也不引入任何新的第三方依赖（HTTP 调用基于标准库）。

功能
====

* **场景 1** —— 用户在竹云 Portal 点击 LIMS 图标，竹云带 ``code`` 直接回调
  ``/@@oauth2-callback``。
* **场景 2** —— 用户直接访问 LIMS，未登录时被送到竹云授权页，认证后带
  ``code`` + ``state`` 回调。
* 用授权码换 ``access_token``（Basic 认证 + 表单提交），再调 ``userinfo``
  取用户身份。
* ``state`` 用 HMAC 签名的 http-only Cookie 校验，防 CSRF；不依赖 Zope
  session（RelStorage 环境下不可靠）。
* 账号路由：

  * 已存在且已授权 → 建立本地会话，进入 LIMS
  * 已存在但已停用 → ``/@@oauth2-disabled``（账号已被禁用）
  * 不存在 → 自动建号并放入“待授权”组 → ``/@@oauth2-pending``
    （待管理员分配权限）

* **每天一次的用户同步**：调用竹云 EIAM ``/api/v2/tenant/users``，把
  ``disabled`` / ``locked`` / 已从竹云消失的用户在 LIMS 里停用（解决“员工离职、
  客户不提供通知接口”的问题）。
* 退出时可同时调用竹云全局退出接口。
* 管理员逃生出口：``/@@oauth2-local-login`` 始终可以打开本地登录表单。

安装与配置
==========

见 `INSTALL.md <INSTALL.md>`_。

用到的竹云接口
==============

===================================  ==========================================
接口                                  用途
===================================  ==========================================
``GET  /api/v1/oauth2/authorize``     获取标准授权码
``POST /api/v1/oauth2/token``         授权码换 access_token
``GET  /api/v1/oauth2/userinfo``      获取用户身份
``POST /api/v1/oauth2/introspect``    检查 token 有效性（预留）
``GET  /api/v1/logout``               全局退出
``POST /api/v2/tenant/token``         EIAM 鉴权 (client_credentials)
``GET  /api/v2/tenant/users``         EIAM 用户列表（每日同步）
===================================  ==========================================

文档：https://open.bccastle.com/development/
