# -*- coding: utf-8 -*-
"""Persistent mapping between the 竹云 unique id and the local Plone user id.

The 竹云 unique id (external_id) is not usable as a Plone user id -- it is long
and opaque -- and the login name may change over time.  So the mapping is kept
explicitly in an ``OOBTree`` annotated on the portal, which also gives the
daily sync job a cheap way to enumerate exactly the SSO managed accounts.
"""

from BTrees.OOBTree import OOBTree
from zope.annotation.interfaces import IAnnotations

ANNOTATION_KEY = "maitux.oauth2.subjects"


def _annotations(portal):
    return IAnnotations(portal)


def get_registry(portal, create=True):
    """Return the ``subject -> userid`` BTree of the portal."""
    annotations = _annotations(portal)
    mapping = annotations.get(ANNOTATION_KEY)
    if mapping is None:
        if not create:
            return OOBTree()
        mapping = OOBTree()
        annotations[ANNOTATION_KEY] = mapping
    return mapping


def get_userid(portal, subject):
    if not subject:
        return None
    return get_registry(portal, create=False).get(subject)


def set_userid(portal, subject, userid):
    if not subject or not userid:
        return
    get_registry(portal)[subject] = userid


def forget(portal, subject):
    mapping = get_registry(portal, create=False)
    if subject in mapping:
        del mapping[subject]


def items(portal):
    """``[(subject, userid), ...]`` -- materialised so callers may mutate."""
    return list(get_registry(portal, create=False).items())


def subject_for_userid(portal, userid):
    for subject, uid in get_registry(portal, create=False).items():
        if uid == userid:
            return subject
    return None
