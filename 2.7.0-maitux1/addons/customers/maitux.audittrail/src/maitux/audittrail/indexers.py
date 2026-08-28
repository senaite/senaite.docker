# -*- coding: utf-8 -*-
"""Bytes-tolerant auditlog fulltext indexer.

SENAITE core's ``senaite.core.catalog.indexer.auditlog.listing_searchable_text``
appends un-encoded ``bytes`` snapshot values (e.g. GBK-encoded Chinese) into a
``set()`` alongside unicode titles resolved from UIDs. Joining such a mixed set
under Python 2 falls back to ASCII decoding for every byte string, so any
non-ASCII byte (e.g. ``0xc5``) raises::

    UnicodeDecodeError: 'ascii' codec can't decode byte 0xc5 ...

during a catalog re-index, which surfaces as a 500 on 样品接收 (sample receive).

This module re-implements the same indexer but normalises every string to
``unicode`` (``utf-8`` with ``errors='replace'``) before adding it to the set,
so the join can never raise a decoding error.

This is an OVERRIDE of the senaite.core adapter; it must be registered from
``overrides.zcml`` (see R5 in SENAITE-Addon开发规则.md) and loaded via the
``maitux.audittrail-overrides`` package-includes slug.
"""

import itertools
import re

import six

from bika.lims import api
from bika.lims.api.snapshot import get_snapshots
from bika.lims.interfaces import IAuditable
from plone.indexer import indexer
from plone.memoize.ram import DontCache
from plone.memoize.ram import cache
from senaite.core.interfaces import IAuditlogCatalog

UID_RX = re.compile(r"[a-z0-9]{32}$")
DATE_RX = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}")


def _uid_to_title_cache_key(func, uid):
    brain = api.get_brain_by_uid(uid, default=None)
    if brain is None:
        raise DontCache
    modified = api.get_modification_date(brain).millis()
    return "{}-{}".format(uid, modified)


@cache(_uid_to_title_cache_key)
def get_title_or_id_from_uid(uid):
    """Returns the title or ID from the given UID
    """
    obj = api.get_object_by_uid(uid, default=None)
    if obj is None:
        return ""
    title_or_id = api.get_title(obj) or api.get_id(obj)
    return title_or_id


@indexer(IAuditable, IAuditlogCatalog)
def listing_searchable_text(instance):
    """Fulltext search for the audit metadata (bytes-tolerant override)
    """
    # get all snapshots
    snapshots = get_snapshots(instance)
    # extract all snapshot values, because we are not interested in the
    # fieldnames (keys)
    values = map(lambda s: s.values(), snapshots)
    # prepare a set of unified catalog data
    catalog_data = set()
    # values to skip
    skip_values = ["None", "true", "True", "false", "False"]
    # internal uid -> title cache
    uid_title_cache = {}

    # helper function to recursively unpack the snapshot values
    def append(value):
        if isinstance(value, (list, tuple)):
            map(append, value)
        elif isinstance(value, (dict,)):
            map(append, value.items())
        elif isinstance(value, six.string_types):
            # coerce every string to unicode, tolerating any stored encoding
            if isinstance(value, str):
                value = value.decode("utf-8", "replace")
            # skip single short values
            if len(value) < 2:
                return
            # flush non meaningful values
            if value in skip_values:
                return
            # flush ISO dates
            if re.match(DATE_RX, value):
                return
            # fetch the title
            if re.match(UID_RX, value):
                if value in uid_title_cache:
                    value = uid_title_cache[value]
                else:
                    title_or_id = get_title_or_id_from_uid(value)
                    uid_title_cache[value] = title_or_id
                    value = title_or_id
            # final guard: titles resolved from UIDs may still be bytes on Py2
            # (e.g. GBK-encoded obj.Title()); normalize to text before add so
            # the join below never trips the ASCII fallback decode
            if isinstance(value, str):
                value = value.decode("utf-8", "replace")
            catalog_data.add(value)

    # extract all meaningful values
    for value in itertools.chain(values):
        append(value)

    return " ".join(catalog_data)