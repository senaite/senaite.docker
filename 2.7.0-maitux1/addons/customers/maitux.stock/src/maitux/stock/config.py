from Products.CMFCore.permissions import AddPortalContent
from Products.CMFCore.permissions import ManagePortal

PROJECTNAME = "maitux.stock"

ADD_CONTENT_PERMISSIONS = {
    'StockItem': AddPortalContent,
    'StockFolder': ManagePortal,
}

