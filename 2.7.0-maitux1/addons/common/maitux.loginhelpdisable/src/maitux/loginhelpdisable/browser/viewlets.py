from plone.app.layout.viewlets.common import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile


class HideLoginHelpLinkViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/loginhelp_hide.pt")
