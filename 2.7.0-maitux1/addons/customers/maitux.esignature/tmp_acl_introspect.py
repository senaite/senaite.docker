from plone import api
portal = api.portal.get()
acl = api.portal.get_tool('acl_users')
print('ACL_CLASS=%s' % acl.__class__.__name__)
for name in ['authenticateCredentials','validateCredentials','authenticate','plugins']:
    print('%s=%s' % (name, hasattr(acl, name)))
plugins = getattr(acl, 'plugins', None)
print('PLUGINS_CLASS=%s' % (plugins.__class__.__name__ if plugins else 'None'))
if plugins:
    from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin
    from Products.PluggableAuthService.interfaces.plugins import ICredentialsUpdatePlugin
    try:
        auth_plugins = plugins.listPlugins(IAuthenticationPlugin)
        print('AUTH_PLUGIN_COUNT=%s' % len(auth_plugins))
        for pid, plugin in auth_plugins:
            print('AUTH_PLUGIN=%s:%s:%s' % (pid, plugin.__class__.__module__, plugin.__class__.__name__))
            print('HAS_AUTHCRED=%s' % hasattr(plugin, 'authenticateCredentials'))
        cred_plugins = plugins.listPlugins(ICredentialsUpdatePlugin)
        print('CRED_UPDATE_COUNT=%s' % len(cred_plugins))
    except Exception as exc:
        print('PLUGIN_ERROR=%s' % exc)
