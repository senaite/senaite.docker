# -*- coding: utf-8 -*-
from bika.lims import api
from senaite.core.catalog import SETUP_CATALOG
from zope.interface import implementer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary


@implementer(IVocabularyFactory)
class SuppliersVocabularyFactory(object):
    def __call__(self, context):
        catalog = api.get_tool(SETUP_CATALOG)
        brains = catalog(
            portal_type="Supplier",
            is_active=True,
            sort_on="sortable_title",
            sort_order="ascending",
        )
        terms = []
        for brain in brains:
            uid = getattr(brain, "UID", None)
            if not uid:
                continue
            title = api.get_title(brain) or uid
            terms.append(SimpleTerm(value=uid, token=uid, title=title))
        return SimpleVocabulary(terms)

