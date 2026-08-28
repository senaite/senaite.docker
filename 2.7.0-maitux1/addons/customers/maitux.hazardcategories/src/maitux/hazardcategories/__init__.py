# -*- coding: utf-8 -*-
import logging
import sys

from zope.i18nmessageid import MessageFactory

PROJECTNAME = "maitux.hazardcategories"
_ = MessageFactory(PROJECTNAME)
logger = logging.getLogger(PROJECTNAME)


def _install_arextension_pickle_aliases():
    """Make historical pickle refs of maitux.arextension.* resolve to INNOCARE.arextension.*.

    Historical DB objects were pickled against the old ``maitux.arextension``
    egg. After renaming the egg to ``INNOCARE.arextension``, unpickling such
    objects fails with::

        PicklingError: Import of module
        maitux.arextension.extenders.analysisrequest failed

    Registering the current modules under their former dotted paths in
    ``sys.modules`` lets pickle resolve the old names to the new module
    objects and class objects without touching the pickled data.
    """
    try:
        import INNOCARE.arextension
        import INNOCARE.arextension.extenders
        import INNOCARE.arextension.extenders.analysisrequest
    except ImportError as e:
        logger.warn(
            "maitux.hazardcategories: INNOCARE.arextension not importable, "
            "skip pickle alias installation: %s" % e
        )
        return

    aliases = [
        ("maitux.arextension", INNOCARE.arextension),
        ("maitux.arextension.extenders", INNOCARE.arextension.extenders),
        (
            "maitux.arextension.extenders.analysisrequest",
            INNOCARE.arextension.extenders.analysisrequest,
        ),
    ]
    for old_name, mod in aliases:
        if old_name in sys.modules and sys.modules[old_name] is mod:
            continue
        if old_name in sys.modules and sys.modules[old_name] is not mod:
            logger.warn(
                "maitux.hazardcategories pickle alias skipped for %s: "
                "sys.modules already bound to %s"
                % (old_name, sys.modules[old_name].__name__)
            )
            continue
        sys.modules[old_name] = mod
        logger.info(
            "maitux.hazardcategories pickle alias: %s -> %s"
            % (old_name, mod.__name__)
        )


_install_arextension_pickle_aliases()

from maitux.hazardcategories import patches  # noqa: E402,F401
