# -*- coding: utf-8 -*-
"""Setup tests for this package."""
from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from senaite.oidc.testing import SENAITE_OIDC_INTEGRATION_TESTING  # noqa: E501

import unittest


try:
    from Products.CMFPlone.utils import get_installer
except ImportError:
    get_installer = None


class TestSetup(unittest.TestCase):
    """Test that senaite.oidc is properly installed."""

    layer = SENAITE_OIDC_INTEGRATION_TESTING

    def setUp(self):
        """Custom shared utility setup for tests."""
        self.portal = self.layer['portal']
        if get_installer:
            self.installer = get_installer(self.portal, self.layer['request'])
        else:
            self.installer = api.portal.get_tool('portal_quickinstaller')

    def test_product_installed(self):
        """Test if senaite.oidc is installed."""
        self.assertTrue(self.installer.isProductInstalled(
            'senaite.oidc'))

    def test_browserlayer(self):
        """Test that ISenaiteOidcLayer is registered."""
        from senaite.oidc.interfaces import (
            ISenaiteOidcLayer)
        from plone.browserlayer import utils
        self.assertIn(
            ISenaiteOidcLayer,
            utils.registered_layers())


class TestUninstall(unittest.TestCase):

    layer = SENAITE_OIDC_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer['portal']
        if get_installer:
            self.installer = get_installer(self.portal, self.layer['request'])
        else:
            self.installer = api.portal.get_tool('portal_quickinstaller')
        roles_before = api.user.get_roles(TEST_USER_ID)
        setRoles(self.portal, TEST_USER_ID, ['Manager'])
        self.installer.uninstallProducts(['senaite.oidc'])
        setRoles(self.portal, TEST_USER_ID, roles_before)

    def test_product_uninstalled(self):
        """Test if senaite.oidc is cleanly uninstalled."""
        self.assertFalse(self.installer.isProductInstalled(
            'senaite.oidc'))

    def test_browserlayer_removed(self):
        """Test that ISenaiteOidcLayer is removed."""
        from senaite.oidc.interfaces import \
            ISenaiteOidcLayer
        from plone.browserlayer import utils
        self.assertNotIn(
            ISenaiteOidcLayer,
            utils.registered_layers())
