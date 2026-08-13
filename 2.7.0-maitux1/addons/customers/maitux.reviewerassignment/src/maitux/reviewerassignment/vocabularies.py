# -*- coding: utf-8 -*-
"""自定义词汇表工厂

为 schema.Choice 字段提供动态下拉选项。
"""

from bika.lims import api
from senaite.core.catalog import SETUP_CATALOG
from zope.interface import implementer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary


# ============ 示例词汇表（可按需启用） ============

# @implementer(IVocabularyFactory)
# class YourVocabularyFactory(object):
#     """示例：从 SETUP_CATALOG 查询活跃对象构建词汇表"""
#     def __call__(self, context):
#         catalog = api.get_tool(SETUP_CATALOG)
#         brains = catalog(
#             portal_type="Supplier",
#             is_active=True,
#             sort_on="sortable_title",
#             sort_order="ascending",
#         )
#         terms = []
#         for brain in brains:
#             uid = getattr(brain, "UID", None)
#             if not uid:
#                 continue
#             title = api.get_title(brain) or uid
#             terms.append(SimpleTerm(value=uid, token=uid, title=title))
#         return SimpleVocabulary(terms)
