# -*- coding: utf-8 -*-

from senaite.core.config.vocabularies import RESULT_TYPES as CORE_RESULT_TYPES
from maitux.calcenhance.config.vocabularies import ADDITIONAL_RESULT_TYPES
from zope.interface import implementer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleVocabulary


@implementer(IVocabularyFactory)
class ResultTypesVocabulary(object):
    """Extends the core RESULT_TYPES vocabulary with List and Calculated."""

    def __call__(self, context=None):
        all_types = list(CORE_RESULT_TYPES) + list(ADDITIONAL_RESULT_TYPES)
        # Remove duplicates (keep first occurrence)
        seen = set()
        unique = [(v, t) for v, t in all_types
                  if v not in seen and not seen.add(v)]
        terms = [SimpleVocabulary.createTerm(v, v, t) for v, t in unique]
        return SimpleVocabulary(terms)


ResultTypesVocabularyFactory = ResultTypesVocabulary()
