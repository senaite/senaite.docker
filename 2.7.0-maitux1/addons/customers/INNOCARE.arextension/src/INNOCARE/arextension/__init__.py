# -*- coding: utf-8 -*-
import logging
import sys
from zope.i18nmessageid import MessageFactory

AREXTENSION_DOMAIN = "INNOCARE.arextension"
_ = MessageFactory(AREXTENSION_DOMAIN)
logger = logging.getLogger(AREXTENSION_DOMAIN)


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
            "INNOCARE.arextension: submodules not importable, "
            "skip pickle alias installation: %s" % e
        )
        return

    # 注意：本函数在 INNOCARE.arextension 的 __init__.py 里执行。此时该子包
    # 正处于首次 import 过程中，父包 INNOCARE 上的 "arextension" 属性尚未绑定
    # （要等本 __init__ 跑完才绑定），因此不能写成 INNOCARE.arextension 这样的
    # 属性链，否则会抛 AttributeError。改为直接从 sys.modules 取模块对象。
    aliases = [
        ("maitux.arextension", sys.modules["INNOCARE.arextension"]),
        (
            "maitux.arextension.extenders",
            sys.modules["INNOCARE.arextension.extenders"],
        ),
        (
            "maitux.arextension.extenders.analysisrequest",
            sys.modules["INNOCARE.arextension.extenders.analysisrequest"],
        ),
    ]
    for old_name, mod in aliases:
        if old_name in sys.modules and sys.modules[old_name] is mod:
            continue
        if old_name in sys.modules and sys.modules[old_name] is not mod:
            logger.warn(
                "INNOCARE.arextension pickle alias skipped for %s: "
                "sys.modules already bound to %s"
                % (old_name, sys.modules[old_name].__name__)
            )
            continue
        sys.modules[old_name] = mod
        logger.info(
            "INNOCARE.arextension pickle alias: %s -> %s"
            % (old_name, mod.__name__)
        )


_install_arextension_pickle_aliases()

from INNOCARE.arextension import patches  # noqa: E402,F401
