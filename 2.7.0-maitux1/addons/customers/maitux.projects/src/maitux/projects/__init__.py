# -*- coding: utf-8 -*-
import logging
import sys

from zope.i18nmessageid import MessageFactory

PROJECTNAME = "maitux.projects"
_ = MessageFactory(PROJECTNAME)

logger = logging.getLogger(PROJECTNAME)


def _install_pickle_aliases():
    """Make historical pickle refs of INNOCARE.projects.* resolve to
    maitux.projects.*.

    Objects stored in the ZODB before the package rename (e.g. the "projects"
    folder and Project items) were pickled against the old dotted module
    paths. Registering the current modules under their former names in
    ``sys.modules`` lets pickle resolve the old references without touching
    the pickled data.
    """
    try:
        import maitux.projects
        import maitux.projects.config
        import maitux.projects.interfaces
        import maitux.projects.setuphandlers
        import maitux.projects.content
        import maitux.projects.content.projects
        import maitux.projects.content.project
        import maitux.projects.browser
        import maitux.projects.browser.controlpanel
    except ImportError as e:
        logger.warn("maitux.projects: pickle alias installation skipped: %s", e)
        return
    # Python 2 does not set the parent-package attribute when the submodule is
    # already registered in sys.modules (this package is mid-import right now),
    # so `maitux.projects` would not resolve below. Bind the attribute
    # explicitly BEFORE referencing it.
    try:
        import maitux
        setattr(maitux, "projects", sys.modules[__name__])
    except Exception:
        pass
    mods = {
        "INNOCARE.projects": maitux.projects,
        "INNOCARE.projects.config": maitux.projects.config,
        "INNOCARE.projects.interfaces": maitux.projects.interfaces,
        "INNOCARE.projects.setuphandlers": maitux.projects.setuphandlers,
        "INNOCARE.projects.content": maitux.projects.content,
        "INNOCARE.projects.content.projects": maitux.projects.content.projects,
        "INNOCARE.projects.content.project": maitux.projects.content.project,
        "INNOCARE.projects.browser": maitux.projects.browser,
        "INNOCARE.projects.browser.controlpanel": maitux.projects.browser.controlpanel,
    }
    for old_name, mod in mods.items():
        if old_name in sys.modules and sys.modules[old_name] is mod:
            continue
        sys.modules[old_name] = mod
        logger.info("maitux.projects pickle alias: %s -> %s",
                    old_name, mod.__name__)


_install_pickle_aliases()
