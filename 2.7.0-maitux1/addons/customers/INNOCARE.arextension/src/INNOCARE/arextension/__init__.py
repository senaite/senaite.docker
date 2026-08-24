# -*- coding: utf-8 -*-
import logging
from zope.i18nmessageid import MessageFactory

AREXTENSION_DOMAIN = "INNOCARE.arextension"
_ = MessageFactory(AREXTENSION_DOMAIN)
logger = logging.getLogger(AREXTENSION_DOMAIN)

from INNOCARE.arextension import patches  # noqa: F401
