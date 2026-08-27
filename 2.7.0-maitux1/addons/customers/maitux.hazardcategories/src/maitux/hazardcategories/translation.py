# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from maitux.hazardcategories import PROJECTNAME


def _to_unicode(text):
    if text is None:
        return u""
    if isinstance(text, bytes):
        try:
            return text.decode("utf-8")
        except Exception:
            try:
                return text.decode("utf-8", "ignore")
            except Exception:
                return u""
    return unicode(text)


def _to_bytes(text):
    if isinstance(text, unicode):
        return text.encode("utf-8")
    return text


def _msg_accessors(obj):
    if obj is None:
        return (None, None, None)
    if "Message" not in type(obj).__name__:
        return (None, None, None)
    msgid = unicode(obj) if isinstance(obj, basestring) else None
    domain = None
    default = None
    try:
        cls = type(obj)
        d = getattr(cls, "domain", None)
        if d is not None and hasattr(d, "__get__"):
            domain = d.__get__(obj, cls)
    except Exception:
        domain = None
    try:
        cls = type(obj)
        d = getattr(cls, "default", None)
        if d is not None and hasattr(d, "__get__"):
            default = d.__get__(obj, cls)
    except Exception:
        default = None
    return (msgid, domain, default)


def translate_with_fallback(msg, context=None, languages=None, domain=None):
    if msg is None:
        return u""
    msgid, _, _ = _msg_accessors(msg)
    try:
        default = _msg_accessors(msg)[2]
    except Exception:
        default = u""
    default = default or u""
    if languages is None:
        languages = (None, "zh_CN", "zh-cn", "zh", "en")
    if domain is None:
        domain = PROJECTNAME
    try:
        from zope.i18n import translate as zt
    except Exception:
        return _to_unicode(default) or _to_unicode(msg)

    result = None
    try:
        result = zt(msg, context=context, domain=domain)
    except Exception:
        result = None
    result_uni = _to_unicode(result) if result else u""
    default_uni = _to_unicode(default)
    msgid_uni = _to_unicode(msgid)
    if result_uni and result_uni != default_uni and result_uni != msgid_uni:
        return result_uni
    for lang in languages:
        try:
            if lang is None:
                candidate = zt(msg, context=context, domain=domain)
            else:
                candidate = zt(msg, target_language=lang,
                                context=context, domain=domain)
        except Exception:
            candidate = None
        cand_uni = _to_unicode(candidate) if candidate else u""
        if cand_uni and cand_uni != default_uni and cand_uni != msgid_uni:
            return cand_uni
    return result_uni or default_uni or _to_unicode(msg)
