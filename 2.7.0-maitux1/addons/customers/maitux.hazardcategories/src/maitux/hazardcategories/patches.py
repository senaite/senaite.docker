# -*- coding: utf-8 -*-

from bika.lims.content import referencedefinition as core_refdef_module
from bika.lims.content import referencesample as core_refsample_module
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


class LiveHazardCategories(object):
    """Read-only sequence view over the editable hazard categories.

    ``senaite.core`` keeps its categories in the module level constant
    ``HAZARD_CATEGORIES``, and some of its modules bind that name at import
    time (``from ... import HAZARD_CATEGORIES``). Rebinding those names to
    this object makes them follow the categories managed by this add-on
    instead of the hardcoded tuple.

    Lookups are deferred to access time on purpose: ``get_categories()``
    reads the hazard categories folder / catalog / registry and therefore
    needs a site, which is not available while ZCML is being loaded. The
    core tuple is kept as fallback, so on any read error the behaviour is
    the one we had before patching.
    """

    def __init__(self, fallback):
        self.fallback = fallback

    def categories(self):
        try:
            categories = get_categories()
        except Exception as e:
            logger.warn(
                "maitux.hazardcategories: cannot read the editable hazard "
                "categories, falling back to the ones of senaite.core: %s" % e)
            return self.fallback
        return categories or self.fallback

    def __iter__(self):
        return iter(self.categories())

    def __len__(self):
        return len(self.categories())

    def __getitem__(self, index):
        return self.categories()[index]

    def __contains__(self, item):
        return item in self.categories()

    def __repr__(self):
        return "<LiveHazardCategories %r>" % (self.categories(),)


HAZARD_CATEGORIES = LiveHazardCategories(
    core_hazard_categories.HAZARD_CATEGORIES)

ReferenceDefinition.getHazardCategoriesVocabulary = get_hazard_categories_vocabulary
ReferenceSample.getHazardCategoriesVocabulary = get_hazard_categories_vocabulary
core_hazard_categories.get_category = patched_core_get_category
core_hazard_categories.format_title = patched_core_format_title
core_hazard_categories.HAZARD_CATEGORIES = HAZARD_CATEGORIES
hazard_api.get_category = patched_core_get_category
hazard_api.format_title = patched_core_format_title

# ``bika.lims.content.referencedefinition`` and
# ``bika.lims.content.referencesample`` bind ``format_title`` and
# ``HAZARD_CATEGORIES`` at import time, so patching the core module above does
# not reach them. Rebind the names in those modules as well.
for _module in (core_refdef_module, core_refsample_module):
    _module.format_title = patched_core_format_title
    _module.HAZARD_CATEGORIES = HAZARD_CATEGORIES

# NOTE: do *not* patch
# ``core_hazard_categories.HazardCategoriesVocabularyFactory`` here. That
# vocabulary is overridden the regular way in ``overrides.zcml``, with
# ``.utils.EditableHazardCategoriesVocabulary`` registered under the same
# utility name. Replacing the factory object on the core module instead makes
# the instance fail to start: the ``<utility component=... />`` directive of
# ``senaite.core`` declares no explicit ``provides``, so zope.component infers
# the interface from the object and raises
# ``TypeError: Missing 'provides' attribute`` for any replacement that does
# not provide exactly one interface.

logger.info("maitux.hazardcategories patches loaded")
