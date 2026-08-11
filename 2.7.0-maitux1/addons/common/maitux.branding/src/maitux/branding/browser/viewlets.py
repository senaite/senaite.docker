from plone.app.layout.viewlets.common import FooterViewlet as BaseFooterViewlet
from plone.app.layout.viewlets.common import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile


class FooterViewlet(BaseFooterViewlet):
    index = ViewPageTemplateFile("templates/footer.pt")


class ColophonViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/colophon.pt")


class TitleViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/title.pt")
