from Products.Five import BrowserView
from zExceptions import NotFound


class DisabledLoginHelpView(BrowserView):

    def __call__(self):
        raise NotFound(self.context, self.__name__, self.request)
