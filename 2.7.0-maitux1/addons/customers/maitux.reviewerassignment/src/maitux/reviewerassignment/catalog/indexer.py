# -*- coding: utf-8 -*-
"""审核人索引"""

from plone.indexer import indexer
from senaite.core.interfaces import IWorksheet
from senaite.core.interfaces.catalog import IWorksheetCatalog

from maitux.reviewerassignment.behaviors.reviewer import (
    IWorksheetReviewerBehavior,
)


@indexer(IWorksheet, IWorksheetCatalog)
def get_reviewer_userid(instance):
    """返回工作表审核人用户 id"""
    try:
        behavior = IWorksheetReviewerBehavior(instance)
    except TypeError:
        return u""
    return behavior.reviewer_userid or u""
