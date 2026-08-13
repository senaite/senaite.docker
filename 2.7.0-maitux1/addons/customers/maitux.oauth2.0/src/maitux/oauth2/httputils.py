# -*- coding: utf-8 -*-
"""Minimal JSON/HTTP helper built on the standard library.

``requests`` is deliberately avoided: this add-on has to run inside a very
tightly pinned Python 2.7 buildout and pulling in ``requests`` would drag
``urllib3``/``certifi``/``charset-normalizer`` resolution into the image build.
"""

import base64
import json
import socket
import ssl

from six.moves.urllib.error import HTTPError
from six.moves.urllib.error import URLError
from six.moves.urllib.parse import urlencode
from six.moves.urllib.request import Request
from six.moves.urllib.request import urlopen

from maitux.oauth2 import logger
from maitux.oauth2 import safe_text


class HttpError(Exception):
    """Raised when the IDaaS could not be reached or answered with garbage."""

    def __init__(self, message, status=None, body=None):
        super(HttpError, self).__init__(message)
        self.status = status
        self.body = body


def _as_bytes(value):
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def basic_auth_header(client_id, client_secret):
    """``Basic base64(client_id:client_secret)`` as required by 竹云."""
    raw = _as_bytes(u"%s:%s" % (client_id or u"", client_secret or u""))
    return u"Basic %s" % base64.b64encode(raw).decode("ascii")


def _ssl_context(verify_ssl):
    if verify_ssl:
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def request_json(url, method="GET", form=None, headers=None, timeout=15,
                 verify_ssl=True):
    """Perform an HTTP request and decode the JSON body.

    Returns a ``(status, data)`` tuple.  ``data`` is the decoded JSON body, or
    ``{"_raw": <text>}`` when the body is not valid JSON.  Non-2xx responses are
    returned too (竹云 puts ``error``/``error_description`` in the body), only
    transport level problems raise :class:`HttpError`.
    """
    body = None
    all_headers = {"Accept": "application/json"}
    if form is not None:
        body = _as_bytes(urlencode(form))
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    all_headers.update(headers or {})

    request = Request(url, data=body)
    for key, value in all_headers.items():
        request.add_header(key, value)
    # urllib uses POST as soon as `data` is given; force the verb explicitly so
    # that GET-with-body or PUT stay possible.
    request.get_method = lambda: method

    context = _ssl_context(verify_ssl) if url.lower().startswith("https") else None

    try:
        if context is not None:
            response = urlopen(request, timeout=timeout, context=context)
        else:
            response = urlopen(request, timeout=timeout)
        status = response.getcode()
        raw = response.read()
        response.close()
    except HTTPError as exc:
        status = exc.code
        try:
            raw = exc.read()
        except Exception:
            raw = b""
    except (URLError, socket.error, ssl.SSLError) as exc:
        logger.error("%s %s failed: %s", method, url, safe_text(exc))
        raise HttpError(u"无法连接竹云服务：%s" % safe_text(exc))

    text = _as_text(raw or b"")
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        data = {"_raw": text}

    if not isinstance(data, dict):
        data = {"_raw": data}

    return status, data
