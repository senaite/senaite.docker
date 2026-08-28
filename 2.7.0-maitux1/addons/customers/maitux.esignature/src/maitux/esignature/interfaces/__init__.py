# -*- coding: utf-8 -*-
"""Interfaces for the MEDAI  electronic signature add-on."""

from plone.supermodel import model
from plone.theme.interfaces import IDefaultPloneLayer
from senaite.core.interfaces import ISenaiteCore
from zope import schema
from zope.interface import Interface


class IMedaiSenaiteESignatureLayer(ISenaiteCore, IDefaultPloneLayer):
    """Browser layer for the electronic signature add-on."""


class IESignatureControlPanelSettings(model.Schema):
    """Registry schema for the MVP add-on settings."""

    enabled = schema.Bool(
        title=u"Enable electronic signature MVP",
        description=u"Turn the electronic signature gate on or off.",
        default=True,
        required=False,
    )

    auditlog_summary_enabled = schema.Bool(
        title=u"Show signature summary in AuditLog",
        description=u"Keep the signature record, but optionally hide the AuditLog summary.",
        default=True,
        required=False,
    )

    verified_context_ttl_seconds = schema.Int(
        title=u"Verified context TTL in seconds",
        description=u"How long a verified signature context stays valid before the transition is executed.",
        default=300,
        required=False,
        min=30,
    )

    pilot_portal_type = schema.TextLine(
        title=u"Pilot portal type",
        description=u"Portal type that requires electronic signature in the current pilot scope.",
        default=u"Analysis",
        required=False,
    )

    pilot_transition = schema.TextLine(
        title=u"Pilot transition",
        description=u"Workflow transition that requires electronic signature in the current pilot scope.",
        default=u"verify",
        required=False,
    )

    signature_type = schema.TextLine(
        title=u"Signature type",
        description=u"Logical signature type stored with successful signature records.",
        default=u"verification",
        required=False,
    )

    meaning_required = schema.Bool(
        title=u"Meaning is required",
        description=u"Require users to fill the Meaning field before continuing.",
        default=True,
        required=False,
    )

    reason_required = schema.Bool(
        title=u"Reason is required",
        description=u"Require users to fill the Reason field before continuing.",
        default=True,
        required=False,
    )

    policy_rules_json = schema.Text(
        title=u"Policy rules JSON",
        description=u"Internal storage used by the table-based configuration UI.",
        default=u"[]",
        required=False,
    )

    auth_backend = schema.TextLine(
        title=u"Authentication backend",
        description=(
            u"Which identity source verifies the signer's credentials. The "
            u"options are the registered re-authentication providers; a site "
            u"using single sign-on selects the provider of that integration "
            u"instead of the local accounts."
        ),
        default=u"pas",
        required=False,
    )

    meaning_vocabulary = schema.Text(
        title=u"Signature meanings",
        description=(
            u"One meaning per line. These are the values a rule may assign to "
            u"a signature; the signer sees the one configured for the action "
            u"and cannot change it. 21 CFR Part 11 requires the meaning to be "
            u"recorded but does not fix the wording, so adjust these to your "
            u"SOP."
        ),
        default=u"Approval\nReview\nResponsibility\nAuthorship",
        required=False,
    )


class ISignaturePolicyResolver(Interface):
    """Resolve whether a transition requires electronic signature."""

    def resolve(context, transition_id, user_id=None):
        """Return a policy mapping for the context and transition."""


class IReAuthenticationProvider(Interface):
    """Authenticate the current user through the same backend chain as login.

    Registered as a named utility, the name being `backend_id`. The site picks
    one through the `auth_backend` registry record.

    A provider lives in whichever add-on knows that identity source. This
    package owns the contract and ships the local one; an SSO integration
    registers its own and imports only this interface, so the dependency runs
    from the SSO add-on towards the signature contract and never back.
    """

    backend_id = schema.TextLine(
        title=u"Provider backend id",
        required=True,
    )

    title = schema.TextLine(
        title=u"Human readable name, shown in the control panel",
        required=False,
    )

    def authenticate_current_user(user_id, credential, request_context=None):
        """Return a result mapping for the current-user re-auth attempt."""

    def supports_interactive_reauth():
        """Return True when the provider supports password-based re-auth."""

