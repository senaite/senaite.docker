from maitux.capabilityinventory import logger


def pre_install(portal_setup):
    logger.info("MAITUX.CAPABILITYINVENTORY pre-install handler [BEGIN]")
    logger.info("MAITUX.CAPABILITYINVENTORY pre-install handler [DONE]")


def post_install(portal_setup):
    logger.info("MAITUX.CAPABILITYINVENTORY install handler [BEGIN]")
    logger.info("MAITUX.CAPABILITYINVENTORY install handler [DONE]")


def pre_uninstall(portal_setup):
    logger.info("MAITUX.CAPABILITYINVENTORY pre-uninstall handler [BEGIN]")
    logger.info("MAITUX.CAPABILITYINVENTORY pre-uninstall handler [DONE]")


def post_uninstall(portal_setup):
    logger.info("MAITUX.CAPABILITYINVENTORY uninstall handler [BEGIN]")
    logger.info("MAITUX.CAPABILITYINVENTORY uninstall handler [DONE]")

