# -*- coding: utf-8 -*-
"""GenericSetup upgrade steps for maitux.worksheet."""

import logging

logger = logging.getLogger("maitux.worksheet")

PROFILE_ID = "profile-maitux.worksheet:default"


def import_registry(tool):
    """(Re)import the addon's registry records into the site.

    senaite.core's `get_registry_interfaces()` builds its list of schemas from
    the `interfaceName` of the records already stored in the site registry --
    an interface nothing has written a record for is simply never looked at.
    Running the `plone.app.registry` step is therefore what makes
    `sample_analyses_layout` resolvable and puts the field on
    /senaite-controlpanel.

    Idempotent: the importer adds the records the schema declares and leaves
    the values a site has already stored alone.
    """
    tool.runImportStepFromProfile(PROFILE_ID, "plone.app.registry",
                                  run_dependencies=False)
    logger.info("maitux.worksheet: registry records imported")
