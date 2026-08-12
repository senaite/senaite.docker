# -*- coding: utf-8 -*-
import json
import logging

from bika.lims import api
from Products.Five import BrowserView
from plone.protect.interfaces import IDisableCSRFProtection
from zope.interface import alsoProvides

from maitux.instrument_acquisition import forwarder

logger = logging.getLogger("maitux.instrument_acquisition.api")


def _json_response(request, data, status=200):
    """返回 JSON 响应。"""
    request.response.setHeader("Content-Type", "application/json; charset=utf-8")
    request.response.setHeader("Cache-Control", "no-store")
    request.response.setStatus(status)
    return json.dumps(data, ensure_ascii=False)


class InstrumentAcquisitionAPI(BrowserView):
    """仪器采集 API 基类。"""

    def __call__(self):
        alsoProvides(self.request, IDisableCSRFProtection)
        return self.handle_request()

    def handle_request(self):
        """处理请求，供子类重写。"""
        return _json_response(self.request, {
            "success": False,
            "message": "Not implemented",
        }, status=501)


class ForwardTestAPI(InstrumentAcquisitionAPI):
    """测试 HTTP 转发 API。"""

    def handle_request(self):
        """测试转发功能。"""
        uid = self.request.get("uid")
        if not uid:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing template UID",
            }, status=400)

        try:
            template = api.get_object(uid)
        except Exception:
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template UID",
            }, status=404)

        if not api.is_object(template) or api.get_portal_type(template) != "InstrumentParsingTemplate":
            return _json_response(self.request, {
                "success": False,
                "message": "Not an InstrumentParsingTemplate",
            }, status=400)

        # 获取测试数据。
        test_raw = self.request.get("raw_data", "TEST_DATA")
        test_parsed = self.request.get("parsed_data", '{"test": "value"}')

        try:
            test_parsed = json.loads(test_parsed)
        except Exception:
            pass

        # 执行转发。
        data_forwarder = forwarder.DataForwarder(template)
        if not data_forwarder.is_enabled():
            return _json_response(self.request, {
                "success": False,
                "message": "HTTP forward is not enabled for this template",
                "details": {
                    "forward_enabled": getattr(template, "forward_enabled", False),
                    "forward_url": getattr(template, "forward_url", ""),
                },
            }, status=400)

        success, message = data_forwarder.forward(test_raw, test_parsed)
        last_result = data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {}

        return _json_response(self.request, {
            "success": success,
            "message": message,
            "attempts": last_result.get("attempts", 0),
            "status_code": last_result.get("status_code"),
            "test_data": {
                "raw": test_raw,
                "parsed": test_parsed,
            },
        })


class ForwardHistoryAPI(InstrumentAcquisitionAPI):
    """获取转发历史 API。"""

    def handle_request(self):
        """获取转发历史记录。"""
        uid = self.request.get("uid")
        if not uid:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing template UID",
            }, status=400)

        data_forwarder = forwarder.get_forwarder(uid)
        if not data_forwarder:
            return _json_response(self.request, {
                "success": False,
                "message": "Forwarder not found",
            }, status=404)

        limit = int(self.request.get("limit", 10))
        history = data_forwarder.get_forward_history(limit=limit)

        queue_size = 0
        if hasattr(data_forwarder, "get_queue_size"):
            queue_size = data_forwarder.get_queue_size()

        return _json_response(self.request, {
            "success": True,
            "history": history,
            "queue_size": queue_size,
            "last_result": data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {},
        })


class ForwardStatusAPI(InstrumentAcquisitionAPI):
    """转发状态 API。"""

    def handle_request(self):
        """获取转发状态。"""
        uid = self.request.get("uid")
        if not uid:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing template UID",
            }, status=400)

        try:
            template = api.get_object(uid)
        except Exception:
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template UID",
            }, status=404)

        if not api.is_object(template):
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template object",
            }, status=404)

        data_forwarder = forwarder.get_forwarder(uid)
        forwarder_status = {}
        if data_forwarder:
            forwarder_status = {
                "is_enabled": data_forwarder.is_enabled(),
                "queue_size": data_forwarder.get_queue_size() if hasattr(data_forwarder, "get_queue_size") else 0,
                "last_result": data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {},
            }

        return _json_response(self.request, {
            "success": True,
            "template": {
                "uid": api.get_uid(template),
                "title": api.get_title(template),
                "forward_enabled": getattr(template, "forward_enabled", False),
                "forward_url": getattr(template, "forward_url", ""),
                "forward_method": getattr(template, "forward_method", "POST"),
                "forward_timeout": getattr(template, "forward_timeout", 30),
            },
            "forwarder": forwarder_status,
        })


class TemplatesListAPI(InstrumentAcquisitionAPI):
    """获取模板列表 API。"""

    def handle_request(self):
        """获取所有仪器解析模板。"""
        results = api.search({
            "portal_type": "InstrumentParsingTemplate",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }, catalog="senaite_catalog_setup")

        templates = []
        for brain in results:
            try:
                templates.append({
                    "uid": brain.UID,
                    "title": brain.Title,
                    "url": brain.getURL(),
                })
            except Exception:
                pass

        return _json_response(self.request, {
            "success": True,
            "templates": templates,
        })


class ManualForwardAPI(InstrumentAcquisitionAPI):
    """手动转发数据 API。"""

    def handle_request(self):
        """手动转发数据。"""
        if self.request.method != "POST":
            return _json_response(self.request, {
                "success": False,
                "message": "Method not allowed",
            }, status=405)

        uid = self.request.get("uid")
        if not uid:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing template UID",
            }, status=400)

        try:
            template = api.get_object(uid)
        except Exception:
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template UID",
            }, status=404)

        if not api.is_object(template) or api.get_portal_type(template) != "InstrumentParsingTemplate":
            return _json_response(self.request, {
                "success": False,
                "message": "Not an InstrumentParsingTemplate",
            }, status=400)

        # 获取请求体数据。
        try:
            body = json.loads(self.request.get("BODY", "{}"))
        except Exception:
            body = {}

        raw_data = body.get("raw_data", "")
        parsed_data = body.get("parsed_data", raw_data)

        if not raw_data:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing raw_data",
            }, status=400)

        # 执行转发。
        data_forwarder = forwarder.DataForwarder(template)
        success, message = data_forwarder.forward(raw_data, parsed_data)
        last_result = data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {}

        return _json_response(self.request, {
            "success": success,
            "message": message,
            "attempts": last_result.get("attempts", 0),
            "status_code": last_result.get("status_code"),
            "data": {
                "raw": raw_data,
                "parsed": parsed_data,
            },
        })

