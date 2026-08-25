# -*- coding: utf-8 -*-
"""
maitux.worksheet - AS-Grouped Worksheet rendering mode for SENAITE LIMS
"""

from zope.i18nmessageid import MessageFactory

messageFactory = MessageFactory("maitux.worksheet")


def apply_patches():
    """Entry point: called after ZCML is loaded to apply monkey-patches."""
    pass  # V1.0: template-only mode, no monkey-patches needed
