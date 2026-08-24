# -*- coding: utf-8 -*-

from bika.lims.content.referencedefinition import ReferenceDefinition
from bika.lims.content.referencesample import ReferenceSample
from senaite.core import api as core_api
from senaite.core.api import hazard as hazard_api
from senaite.core.vocabularies import hazard_categories as core_hazard_categories

from maitux.hazardcategories import logger
from maitux.hazardcategories.utils import format_title
from maitux.hazardcategories.utils import get_categories
from maitux.hazardcategories.utils import get_category


def get_hazard_categories_vocabulary(self):
    return [
        (cat["code"], format_title(cat))
        for cat in get_categories()
    ]


def patched_core_format_title(category):
    return format_title(category)


def patched_core_get_category(code):
    return get_category(code)


class PatchedHazardCategoriesVocabulary(object):

    def __call__(self, context):
        from zope.schema.vocabulary import SimpleTerm
        from zope.schema.vocabulary import SimpleVocabulary

        terms = [
            SimpleTerm(
                value=category["code"],
                token=category["code"],
                title=format_title(category),
            )
            for category in get_categories()
        ]
        return SimpleVocabulary(terms)


ReferenceDefinition.getHazardCategoriesVocabulary = get_hazard_categories_vocabulary
ReferenceSample.getHazardCategoriesVocabulary = get_hazard_categories_vocabulary
core_hazard_categories.get_category = patched_core_get_category
core_hazard_categories.format_title = patched_core_format_title
core_hazard_categories.HazardCategoriesVocabularyFactory = PatchedHazardCategoriesVocabulary()
hazard_api.get_category = patched_core_get_category
hazard_api.format_title = patched_core_format_title

logger.info("maitux.hazardcategories patches loaded")
