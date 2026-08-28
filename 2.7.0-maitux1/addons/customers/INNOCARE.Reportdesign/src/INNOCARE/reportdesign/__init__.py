# -*- coding: utf-8 -*-
from zope.i18nmessageid import MessageFactory

REPORTDESIGN_DOMAIN = "INNOCARE.Reportdesign"
_ = MessageFactory(REPORTDESIGN_DOMAIN)

# Allow importing this package's helper functions from restricted page-template
# code, e.g. modules['INNOCARE.reportdesign.utils'] in print templates.
from AccessControl.SecurityInfo import ModuleSecurityInfo

ModuleSecurityInfo("INNOCARE").declarePublic("__path__")
ModuleSecurityInfo("INNOCARE.reportdesign").declarePublic("__path__")
ModuleSecurityInfo("INNOCARE.reportdesign.utils").declarePublic("get_coa_data")
