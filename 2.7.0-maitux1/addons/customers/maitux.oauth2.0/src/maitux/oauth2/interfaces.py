# -*- coding: utf-8 -*-
"""Interfaces / configuration schema for maitux.oauth2."""

from plone.supermodel import model
from senaite.core.interfaces import ISenaiteCore
from zope import schema
from zope.publisher.interfaces.browser import IDefaultBrowserLayer

from maitux.oauth2 import _


class IMaituxOAuth2Layer(ISenaiteCore, IDefaultBrowserLayer):
    """Browser layer of this add-on.

    It derives from both the SENAITE layer and the default Plone layer so that
    the views registered for it reliably win over the stock Plone views we
    override (``require_login``, ``logout``).
    """


class IOAuth2Settings(model.Schema):
    """竹云统一登录（OAuth 2.0）配置

    每一项都可以用环境变量覆盖，环境变量名 = ``MAITUX_OAUTH2_`` + 字段名大写。
    例如 ``MAITUX_OAUTH2_CLIENT_SECRET``。环境变量优先级高于此处的配置。
    """

    # ------------------------------------------------------------------
    model.fieldset(
        "provider",
        label=_(u"竹云对接参数"),
        fields=[
            "enabled",
            "provider_url",
            "app_id",
            "client_id",
            "client_secret",
            "scope",
            "redirect_uri",
            "verify_ssl",
            "request_timeout",
        ],
    )

    enabled = schema.Bool(
        title=_(u"启用统一登录"),
        description=_(u"总开关。关闭后本插件的所有跳转、拦截和同步都不会生效。"),
        default=False,
        required=False,
    )

    provider_url = schema.TextLine(
        title=_(u"竹云 IDaaS 地址"),
        description=_(u"例如 https://passport.innocarepharma.com ，不要带结尾斜杠。"),
        default=u"https://passport.innocarepharma.com",
        required=False,
    )

    app_id = schema.TextLine(
        title=_(u"AppId"),
        description=_(u"竹云为本应用分配的 AppId。仅用于记录与排查，登录流程不使用。"),
        default=u"20260804155456579-E219-3F7069E8F",
        required=False,
    )

    client_id = schema.TextLine(
        title=_(u"ClientId"),
        default=u"3UZLLHBzzxb4uZeKH2GGRxbtZMkqFjaY",
        required=False,
    )

    client_secret = schema.Password(
        title=_(u"ClientSecret"),
        description=_(u"建议通过环境变量 MAITUX_OAUTH2_CLIENT_SECRET 注入，避免写入数据库。"),
        default=u"lAI4L84uKn0MMOnw9qlIYiXSJ9mny4KObo4NrAjy45vxoy46uixB4NfLTyRlGy3h",
        required=False,
    )

    scope = schema.TextLine(
        title=_(u"scope"),
        description=_(u"竹云标准授权码模式固定为 get_user_info。"),
        default=u"get_user_info",
        required=False,
    )

    redirect_uri = schema.TextLine(
        title=_(u"回调地址 redirect_uri"),
        description=_(
            u"必须与在竹云应用中登记的可信回调地址完全一致。"
            u"留空则自动使用 <站点地址>/@@oauth2-callback 。"
        ),
        default=u"",
        required=False,
    )

    verify_ssl = schema.Bool(
        title=_(u"校验 HTTPS 证书"),
        description=_(u"竹云使用自签名证书时才关闭。"),
        default=True,
        required=False,
    )

    request_timeout = schema.Int(
        title=_(u"接口超时（秒）"),
        default=15,
        required=False,
    )

    # ------------------------------------------------------------------
    model.fieldset(
        "endpoints",
        label=_(u"接口路径"),
        description=_(u"竹云标准路径，一般不需要修改。"),
        fields=[
            "authorize_path",
            "token_path",
            "userinfo_path",
            "introspect_path",
            "idp_logout_path",
            "eiam_token_path",
            "eiam_users_path",
        ],
    )

    authorize_path = schema.TextLine(
        title=_(u"授权页"),
        default=u"/api/v1/oauth2/authorize",
        required=False,
    )

    token_path = schema.TextLine(
        title=_(u"换取 Access Token"),
        default=u"/api/v1/oauth2/token",
        required=False,
    )

    userinfo_path = schema.TextLine(
        title=_(u"获取用户信息"),
        default=u"/api/v1/oauth2/userinfo",
        required=False,
    )

    introspect_path = schema.TextLine(
        title=_(u"检查 Token 有效性"),
        default=u"/api/v1/oauth2/introspect",
        required=False,
    )

    idp_logout_path = schema.TextLine(
        title=_(u"竹云全局退出"),
        default=u"/api/v1/logout",
        required=False,
    )

    eiam_token_path = schema.TextLine(
        title=_(u"EIAM 鉴权接口"),
        description=_(u"用户定时同步使用，client_credentials 模式。"),
        default=u"/api/v2/tenant/token",
        required=False,
    )

    eiam_users_path = schema.TextLine(
        title=_(u"EIAM 用户列表接口"),
        default=u"/api/v2/tenant/users",
        required=False,
    )

    # ------------------------------------------------------------------
    model.fieldset(
        "identity",
        label=_(u"身份映射"),
        fields=[
            "userid_claim",
            "username_claim",
            "fullname_claim",
            "email_claim",
            "username_prefix",
            "fallback_email_domain",
        ],
    )

    userid_claim = schema.TextLine(
        title=_(u"唯一 ID 字段"),
        description=_(
            u"userinfo 返回值中作为唯一身份标识的字段名，可填多个用英文逗号分隔，"
            u"按顺序取第一个非空值。默认优先取外部 ID（external_id），"
            u"取不到时退回竹云用户 ID（id）。"
        ),
        default=u"external_id,id",
        required=False,
    )

    username_claim = schema.TextLine(
        title=_(u"登录名字段"),
        description=_(u"用于生成 LIMS 本地用户名，可填多个用英文逗号分隔。"),
        default=u"userName,user_name,preferred_username,id",
        required=False,
    )

    fullname_claim = schema.TextLine(
        title=_(u"姓名字段"),
        default=u"name,fullname",
        required=False,
    )

    email_claim = schema.TextLine(
        title=_(u"邮箱字段"),
        default=u"email,mail",
        required=False,
    )

    username_prefix = schema.TextLine(
        title=_(u"本地用户名前缀"),
        description=_(u"例如填 sso_ 后，竹云的 zhangsan 会创建为 sso_zhangsan。留空表示不加前缀。"),
        default=u"",
        required=False,
    )

    fallback_email_domain = schema.TextLine(
        title=_(u"缺省邮箱域名"),
        description=_(u"竹云未返回邮箱时，用 <用户名>@<该域名> 占位（Plone 要求邮箱非空）。"),
        default=u"sso.local",
        required=False,
    )

    # ------------------------------------------------------------------
    model.fieldset(
        "accounts",
        label=_(u"账号策略"),
        fields=[
            "auto_create_user",
            "link_existing_by_username",
            "auto_activate",
            "pending_group",
            "default_groups",
            "login_pending_users",
            "create_labcontact",
            "enforce_disabled",
        ],
    )

    auto_create_user = schema.Bool(
        title=_(u"首次登录自动建号"),
        description=_(u"关闭后，本地不存在的竹云用户将被拒绝登录。"),
        default=True,
        required=False,
    )

    link_existing_by_username = schema.Bool(
        title=_(u"按用户名关联已有账号"),
        description=_(
            u"首次通过竹云登录时，如果本地已存在同名用户，则把该竹云身份绑定到这个已有账号，"
            u"而不是新建一个。"
        ),
        default=True,
        required=False,
    )

    auto_activate = schema.Bool(
        title=_(u"新账号直接可用"),
        description=_(
            u"开启后，新建账号直接加入下方“默认用户组”，跳过待授权流程。"
            u"默认关闭，符合“首次登录 → 待管理员分配权限”的要求。"
        ),
        default=False,
        required=False,
    )

    pending_group = schema.TextLine(
        title=_(u"待授权用户组"),
        description=_(
            u"新建账号会被放进这个组。管理员给该用户分配任意 LIMS 角色、"
            u"或把他移出本组，即视为已授权。"
        ),
        default=u"oauth2-pending",
        required=False,
    )

    default_groups = schema.List(
        title=_(u"默认用户组"),
        description=_(u"“新账号直接可用”开启时，新账号加入的组，每行一个。"),
        value_type=schema.TextLine(),
        default=[],
        missing_value=[],
        required=False,
    )

    login_pending_users = schema.Bool(
        title=_(u"待授权用户也建立会话"),
        description=_(u"默认关闭：待授权用户只看到提示页，不会真正登录进系统。"),
        default=False,
        required=False,
    )

    create_labcontact = schema.Bool(
        title=_(u"自动创建实验室联系人 (LabContact)"),
        description=_(
            u"默认关闭。开启后，新建账号时会在实验室设置里创建一个 LabContact 并关联该用户，"
            u"这样用户才能被指派为分析员。失败不会阻断登录，只写日志。"
        ),
        default=False,
        required=False,
    )

    enforce_disabled = schema.Bool(
        title=_(u"实时拦截已停用账号"),
        description=_(u"每次请求检查当前用户是否被同步标记为停用，是则强制退出并跳到提示页。"),
        default=True,
        required=False,
    )

    # ------------------------------------------------------------------
    model.fieldset(
        "behaviour",
        label=_(u"登录行为"),
        fields=[
            "auto_redirect",
            "redirect_login_form",
            "show_login_button",
            "sso_logout",
        ],
    )

    auto_redirect = schema.Bool(
        title=_(u"未登录自动跳转竹云"),
        description=_(u"匿名用户访问需要登录的页面时，直接跳到竹云授权页。"),
        default=True,
        required=False,
    )

    redirect_login_form = schema.Bool(
        title=_(u"本地登录页也自动跳转"),
        description=_(
            u"开启后连 /login 也会跳到竹云，即“纯统一登录”模式。"
            u"管理员仍可通过 <站点地址>/@@oauth2-local-login 打开本地登录页"
            u"（该入口会在浏览器上种一个 1 小时的豁免 Cookie）。"
        ),
        default=False,
        required=False,
    )

    show_login_button = schema.Bool(
        title=_(u"在登录页显示“竹云统一登录”按钮"),
        default=True,
        required=False,
    )

    sso_logout = schema.Bool(
        title=_(u"退出时同时注销竹云会话"),
        description=_(u"调用竹云全局退出接口，避免退出后点一下又自动登录回来。"),
        default=True,
        required=False,
    )

    # ------------------------------------------------------------------
    model.fieldset(
        "sync",
        label=_(u"用户定时同步"),
        fields=[
            "sync_enabled",
            "sync_user_id_field",
            "sync_org_id",
            "sync_page_size",
            "sync_deactivate_missing",
            "sync_update_properties",
            "sync_token",
            "last_sync",
            "last_sync_result",
        ],
    )

    sync_enabled = schema.Bool(
        title=_(u"启用用户同步"),
        description=_(u"每天从竹云 EIAM 拉取用户列表，把离职/停用/锁定的用户在 LIMS 里停用。"),
        default=True,
        required=False,
    )

    sync_user_id_field = schema.TextLine(
        title=_(u"同步比对字段"),
        description=_(
            u"EIAM 用户列表中与“唯一 ID 字段”对应的字段名，可填多个用英文逗号分隔。"
        ),
        default=u"external_id,user_id",
        required=False,
    )

    sync_org_id = schema.TextLine(
        title=_(u"限定组织 ID"),
        description=_(u"留空表示同步全部用户。"),
        default=u"",
        required=False,
    )

    sync_page_size = schema.Int(
        title=_(u"每页数量"),
        description=_(u"竹云要求 10-100。"),
        default=100,
        required=False,
    )

    sync_deactivate_missing = schema.Bool(
        title=_(u"竹云中查不到的用户也停用"),
        description=_(u"覆盖“账号被直接删除”的情况。"),
        default=True,
        required=False,
    )

    sync_update_properties = schema.Bool(
        title=_(u"同步姓名和邮箱"),
        default=True,
        required=False,
    )

    sync_token = schema.TextLine(
        title=_(u"同步触发口令"),
        description=_(
            u"外部定时任务调用 <站点地址>/@@oauth2-sync-users?token=xxx 时使用。"
            u"留空则只允许已登录的管理员手动触发。"
        ),
        default=u"",
        required=False,
    )

    last_sync = schema.TextLine(
        title=_(u"上次同步时间"),
        description=_(u"只读，由系统写入。"),
        default=u"",
        required=False,
    )

    last_sync_result = schema.Text(
        title=_(u"上次同步结果"),
        description=_(u"只读，由系统写入。"),
        default=u"",
        required=False,
    )

    # ------------------------------------------------------------------
    model.fieldset(
        "internal",
        label=_(u"内部"),
        fields=["state_secret"],
    )

    state_secret = schema.TextLine(
        title=_(u"state 签名密钥"),
        description=_(u"安装时自动生成，用于给防 CSRF 的 state 参数签名。不要手工清空。"),
        default=u"",
        required=False,
    )
