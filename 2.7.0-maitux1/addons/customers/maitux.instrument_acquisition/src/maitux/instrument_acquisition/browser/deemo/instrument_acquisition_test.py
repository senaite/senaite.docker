# -*- coding: utf-8 -*-
import json
import select
import socket
import subprocess
import tempfile
import threading
import time

try:
    import queue as Queue
except Exception:
    import Queue

try:
    text_type = unicode
except Exception:
    text_type = str
from bika.lims import api
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.protect.interfaces import IDisableCSRFProtection
from senaite.core.catalog.indexer.attachment import extract_text_from_file
from zope.interface import alsoProvides

try:
    from distutils.spawn import find_executable
except Exception:
    find_executable = None

from maitux.instrument_acquisition import forwarder

_SERVER_THREAD = None
_SERVER_SOCKET = None
_STOP_EVENT = threading.Event()
_MESSAGE_QUEUE = Queue.Queue()
_JS_SOURCE = None
_SERVER_STATUS = {
    "running": False,
    "host": None,
    "port": None,
    "template_uid": None,
    "error": None,
    "js_engine": None,
    "script_filename": None,
    "script_size": None,
    "forward_enabled": False,
    "forward_url": None,
    "last_forward_success": None,
    "last_forward_message": "",
    "last_forward_attempts": 0,
    "last_forward_status_code": None,
}


def _json_response(request, data):
    request.response.setHeader("Content-Type", "application/json; charset=utf-8")
    request.response.setHeader("Cache-Control", "no-store")
    return json.dumps(data)


def _ensure_text(value):
    if value is None:
        return u""
    if isinstance(value, text_type):
        raw = value.strip()
        return raw
    raw = value.strip()
    try:
        return raw.decode("utf-8")
    except Exception:
        try:
            return raw.decode("gbk")
        except Exception:
            return raw.decode("latin1", "replace")


def _find_node():
    if find_executable is None:
        return None
    # Try common binary names
    path = find_executable("node")
    if path:
        return path
    # Some distros (e.g. Debian/Ubuntu) may use 'nodejs'
    path = find_executable("nodejs")
    if path:
        return path
    return None


def _run_js_parser(js_source, text):
    node = _find_node()
    if not node:
        return u"[JS parser unavailable: node/nodejs not found]"

    if js_source is None:
        return u"[JS script file missing or unreadable]"
    if isinstance(js_source, str) and len(js_source) == 0:
        return u"[JS script file is empty]"

    if not isinstance(js_source, str):
        try:
            js_source = str(js_source)
        except Exception:
            js_source = ""

    if not isinstance(js_source, str):
        js_source = _ensure_text(js_source).encode("utf-8")

    wrapper = (
        "const fs = require('fs');\n"
        "const input = fs.readFileSync(0, 'utf8');\n"
        "\n"
        + js_source.decode("utf-8", "replace")
        + "\n"
        "let out;\n"
        "try {\n"
        "  if (typeof parse === 'function') out = parse(input);\n"
        "  else if (typeof module !== 'undefined' && module.exports && typeof module.exports.parse === 'function') out = module.exports.parse(input);\n"
        "  else out = input;\n"
        "} catch (e) {\n"
        "  console.error(e && (e.stack || e.toString()) || 'Parser error');\n"
        "  process.exit(2);\n"
        "}\n"
        "if (typeof out === 'object') process.stdout.write(JSON.stringify(out));\n"
        "else process.stdout.write(String(out));\n"
    )

    tmp = tempfile.NamedTemporaryFile(prefix="senaite_js_parser_", suffix=".js", delete=False)
    try:
        tmp.write(wrapper.encode("utf-8"))
        tmp.close()
        p = subprocess.Popen(
            [node, tmp.name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if isinstance(text, text_type):
            payload = text.encode("utf-8")
        else:
            payload = text
        out, err = p.communicate(payload)
        if p.returncode != 0:
            msg = _ensure_text(err or "")
            return u"[JS parse error] {}".format(msg)
        return _ensure_text(out or "")
    finally:
        try:
            import os
            os.unlink(tmp.name)
        except Exception:
            pass


def _get_template_by_uid(uid):
    if not uid:
        return None
    try:
        obj = api.get_object(uid)
    except Exception:
        return None
    if not api.is_object(obj):
        return None
    if api.get_portal_type(obj) != "InstrumentParsingTemplate":
        return None
    return obj


def _get_js_source(template):
    if not template:
        return None
    script_file = getattr(template, "script_file", None)
    if not script_file:
        return None
    data = getattr(script_file, "data", None)
    if data:
        try:
            if hasattr(data, "read"):
                data = data.read()
        except Exception:
            pass
    if not data:
        try:
            if hasattr(script_file, "open"):
                f = script_file.open()
                try:
                    data = f.read()
                finally:
                    try:
                        f.close()
                    except Exception:
                        pass
        except Exception:
            data = None
    if not data:
        return None
    return data


class _UploadedBlob(object):
    """Minimal blob-like wrapper for ad-hoc PDF extraction."""

    def __init__(self, data, content_type, filename):
        self.data = data
        self.contentType = content_type
        self.filename = filename


def _read_upload(upload):
    if not upload:
        return None, None, None

    filename = _ensure_text(getattr(upload, "filename", "")) or "uploaded.pdf"
    content_type = ""
    headers = getattr(upload, "headers", None)
    if headers:
        try:
            content_type = headers.get("content-type", "")
        except Exception:
            content_type = ""
    if not content_type:
        content_type = getattr(upload, "contentType", "") or "application/pdf"

    data = None
    try:
        if hasattr(upload, "seek"):
            upload.seek(0)
    except Exception:
        pass

    try:
        data = upload.read()
    except Exception:
        data = None

    if not data:
        return filename, content_type, None
    return filename, content_type, data


def _find_pdftotext():
    """定位系统中的 pdftotext 可执行文件。"""
    if find_executable is None:
        return None
    return find_executable("pdftotext")


def _extract_pdf_text_with_pdftotext(data, filename):
    """使用系统 pdftotext 直接提取 PDF 文本，优先保留版式。"""
    pdftotext = _find_pdftotext()
    if not pdftotext:
        return u"", u"pdftotext not found in PATH"

    tmp = tempfile.NamedTemporaryFile(
        prefix="senaite_pdf_extract_",
        suffix=".pdf",
        delete=False,
    )
    tmp_path = tmp.name
    try:
        tmp.write(data)
        tmp.close()

        process = subprocess.Popen(
            [pdftotext, "-layout", tmp_path, "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = process.communicate()
        text = _ensure_text(out or u"")
        error = _ensure_text(err or u"")

        if process.returncode != 0:
            return u"", error or u"pdftotext exited with status {}".format(
                process.returncode
            )
        if not text:
            return u"", error or u"pdftotext returned empty output"
        return text, u""
    except Exception as exc:
        return u"", _ensure_text(exc)
    finally:
        try:
            import os
            os.unlink(tmp_path)
        except Exception:
            pass


def _extract_pdf_text(upload):
    filename, content_type, data = _read_upload(upload)
    if not data:
        return False, u"No PDF content uploaded", u"", filename or u""

    blob = _UploadedBlob(data, content_type or "application/pdf", filename or "uploaded.pdf")
    # 优先使用 pdftotext -layout，尽量让不同环境输出一致，
    # 这样 JS 解析脚本可以稳定按“同一行包含多列”的格式处理。
    layout_text, layout_error = _extract_pdf_text_with_pdftotext(
        data, blob.filename)
    if layout_text:
        return (
            True,
            u"PDF text extracted successfully via pdftotext -layout",
            layout_text,
            blob.filename,
        )

    # 如果系统没有 pdftotext，或者执行失败，再回退到 portal_transforms。
    text = extract_text_from_file(blob)
    if text:
        return True, u"PDF text extracted successfully via portal_transforms", text, blob.filename

    message = (
        u"PDF text extraction returned no content. "
        u"pdftotext -layout and portal_transforms both gave empty output"
    )
    if layout_error:
        message = u"{}; pdftotext failed: {}".format(
            message, layout_error)
    else:
        message = u"{}; make sure the PDF contains selectable text".format(
            message)
    return False, message, u"", blob.filename


_SAMPLE_PORTAL_TYPES = ("AnalysisRequest",)


def _brain_to_object(brain):
    """从 catalog brain 安全获取对象。"""
    try:
        return brain.getObject()
    except Exception:
        return None


def _normalize_sample_id(value):
    """统一样品编号用于宽松匹配，处理 O/0 误差和大小写差异。"""
    value = _ensure_text(value).strip().upper()
    return value.replace("O", "0")


def _normalize_result_name(value):
    """统一结果项目名称用于宽松匹配。"""
    value = _ensure_text(value).strip().lower()
    normalized = []
    for char in value:
        if char.isalnum():
            normalized.append(char)
    return u"".join(normalized)


def _get_sample_candidates(sample_id):
    """返回样品编号的候选值，兼容 O/0 混用。"""
    sample_id = _ensure_text(sample_id).strip()
    candidates = []
    for value in (
        sample_id,
        sample_id.upper(),
        sample_id.replace("0", "O"),
        sample_id.replace("O", "0"),
        sample_id.upper().replace("0", "O"),
        sample_id.upper().replace("O", "0"),
    ):
        if value and value not in candidates:
            candidates.append(value)
    return candidates


def _query_sample_catalog(query):
    """统一通过样品 catalog 查询样品对象。"""
    try:
        sample_catalog = api.get_tool("senaite_catalog_sample")
    except Exception:
        sample_catalog = None
    if sample_catalog is None:
        return None

    brains = sample_catalog.unrestrictedSearchResults(**query)
    if not brains:
        return None
    return _brain_to_object(brains[0])


def _find_sample_by_sample_id(sample_id):
    """按样品 ID 查找样品，优先匹配 AR ID，再回退到 ClientSampleID。"""
    sample_id = _ensure_text(sample_id)
    if not sample_id:
        return None, u"", u"Missing sample_id"

    candidates = _get_sample_candidates(sample_id)
    for candidate in candidates:
        sample = _query_sample_catalog({
            "portal_type": _SAMPLE_PORTAL_TYPES,
            "getId": candidate,
        })
        if sample:
            return sample, u"getId", u""

    for candidate in candidates:
        sample = _query_sample_catalog({
            "portal_type": _SAMPLE_PORTAL_TYPES,
            "getClientSampleID": candidate,
        })
        if sample:
            return sample, u"getClientSampleID", u""

    normalized_target = _normalize_sample_id(sample_id)
    sample = _query_sample_catalog({
        "portal_type": _SAMPLE_PORTAL_TYPES,
        "listing_searchable_text": sample_id,
    })
    if sample and _normalize_sample_id(sample.getId()) == normalized_target:
        return sample, u"listing_searchable_text", u""
    if sample and _normalize_sample_id(sample.getClientSampleID()) == normalized_target:
        return sample, u"listing_searchable_text", u""

    return None, u"", u"Sample not found: {}".format(sample_id)


def _rewind_upload(upload):
    if not upload:
        return
    try:
        upload.seek(0)
    except Exception:
        pass
    try:
        f = getattr(upload, "file", None)
        if f and hasattr(f, "seek"):
            f.seek(0)
    except Exception:
        pass


def _create_worksheet_attachment(ws, attachment_file, title):
    if ws is None or attachment_file is None:
        return None
    try:
        _rewind_upload(attachment_file)
        attachment = api.create(ws, "Attachment", title=title or getattr(attachment_file, "filename", "Attachment"))
        attachment.edit(AttachmentFile=attachment_file)
        attachment.processForm()
        attachment.reindexObject()
        return attachment
    except Exception:
        return None


def _append_attachment_to_analysis(analysis, attachment):
    if analysis is None or attachment is None:
        return False
    try:
        others = analysis.getAttachment() or []
        attachments = [other.UID() for other in others]
        if attachment.UID() not in attachments:
            attachments.append(attachment.UID())
            analysis.setAttachment(attachments)
            analysis.reindexObject()
        return True
    except Exception:
        return False


def _attach_to_worksheet_row(analysis, attachment_file, attachment_cache, attachment_title):
    if analysis is None or attachment_file is None:
        return None, u""
    ws = analysis.getWorksheet()
    if ws is None:
        return None, u"No worksheet"
    ws_uid = api.get_uid(ws)
    if not ws_uid:
        return None, u"Worksheet UID missing"
    if attachment_cache is None:
        attachment_cache = {}
    attachment = attachment_cache.get(ws_uid)
    if attachment is None:
        attachment = _create_worksheet_attachment(ws, attachment_file, attachment_title)
        if attachment is None:
            return None, u"Attachment create failed"
        attachment_cache[ws_uid] = attachment
    _append_attachment_to_analysis(analysis, attachment)
    return attachment, u""


def _write_sample_payload(sample_payload):
    """将单个样品对象中的 assignments 写回系统。"""
    if not isinstance(sample_payload, dict):
        return {
            "success": False,
            "status": "error",
            "sample_id": u"",
            "matched_by": u"",
            "updated": [],
            "missing": [],
            "skipped": [{
                "reason": "sample payload must be an object",
            }],
            "available_analyses": [],
            "message": u"Invalid sample payload",
        }

    attachment_file = sample_payload.get("_attachment_file")
    attachment_cache = sample_payload.get("_attachment_cache")
    attachment_title = sample_payload.get("_attachment_title") or u""

    sample_id = _ensure_text(sample_payload.get("sample_id"))
    assignments = sample_payload.get("assignments") or []
    details = {
        "sample_id": sample_id,
        "matched_by": u"",
        "sample_title": u"",
        "sample_url": u"",
        "updated": [],
        "missing": [],
        "skipped": [],
        "available_analyses": [],
        "worksheet_attachments": [],
        "message": u"",
    }

    if not sample_id:
        details["message"] = u"Missing sample_id"
        details["status"] = "error"
        return details

    if not isinstance(assignments, list):
        assignments = []
    if not assignments:
        details["message"] = u"No assignments to write for this sample"
        details["status"] = "noop"
        return details

    sample, matched_by, error = _find_sample_by_sample_id(sample_id)
    if sample is None:
        details["message"] = error
        details["status"] = "error"
        return details

    details["matched_by"] = matched_by
    details["sample_title"] = api.get_title(sample)
    details["sample_url"] = api.get_url(sample)

    analyses = sample.getAnalyses(full_objects=True) or []
    analyses_by_keyword = {}
    analyses_by_name = {}
    analyses_by_interim_keyword = {}
    available_analyses = []
    for analysis in analyses:
        keyword = _ensure_text(analysis.getKeyword())
        service = analysis.getAnalysisService()
        service_title = api.get_title(service) if service else u""
        service_keyword = _ensure_text(service.getKeyword()) if service else u""
        available_analyses.append({
            "analysis_keyword": keyword,
            "analysis_title": api.get_title(analysis),
            "service_keyword": service_keyword,
            "service_title": service_title,
            "path": "/".join(analysis.getPhysicalPath()),
        })
        if keyword and keyword.lower() not in analyses_by_keyword:
            analyses_by_keyword[keyword.lower()] = analysis
        if service_keyword and service_keyword.lower() not in analyses_by_keyword:
            analyses_by_keyword[service_keyword.lower()] = analysis
        for name in (
            keyword,
            service_keyword,
            service_title,
            api.get_title(analysis),
            getattr(analysis, "Title", lambda: u"")(),
        ):
            normalized_name = _normalize_result_name(name)
            if normalized_name and normalized_name not in analyses_by_name:
                analyses_by_name[normalized_name] = analysis

        try:
            interims = analysis.getInterimFields() or []
        except Exception:
            interims = []
        for interim in interims:
            interim_keyword = _ensure_text(interim.get("keyword"))
            if interim_keyword and interim_keyword.lower() not in analyses_by_interim_keyword:
                analyses_by_interim_keyword[interim_keyword.lower()] = analysis

    details["available_analyses"] = available_analyses

    updated = details["updated"]
    missing = details["missing"]
    skipped = details["skipped"]
    updated_analyses = []
    for item in assignments:
        target_type = _ensure_text(item.get("target_type"))
        target_keyword = _ensure_text(item.get("target_keyword"))
        value = item.get("value")

        if not target_keyword:
            skipped.append({
                "target_keyword": u"",
                "reason": "missing target_keyword",
            })
            continue

        is_interim = target_type.lower() == "interim"
        if is_interim:
            analysis = analyses_by_interim_keyword.get(target_keyword.lower())

            if analysis is None:
                missing.append({
                    "target_keyword": target_keyword,
                    "value": value,
                })
                continue

            if isinstance(value, (list, tuple)):
                sanitized = []
                for interim_value in value:
                    sanitized.append(_ensure_text(interim_value))
                value = sanitized
            else:
                value = _ensure_text(value)

            analysis.setInterimValue(target_keyword, value)
            analysis.reindexObject()
            updated_analyses.append(analysis)
            updated.append({
                "analysis_keyword": _ensure_text(analysis.getKeyword()),
                "target_keyword": target_keyword,
                "value": value,
                "analysis_title": api.get_title(analysis),
            })
        else:
            analysis = analyses_by_keyword.get(target_keyword.lower())
            if analysis is None:
                analysis = analyses_by_name.get(_normalize_result_name(target_keyword))
            if analysis is None:
                missing.append({
                    "analysis_keyword": target_keyword,
                    "value": value,
                })
                continue

            value = _ensure_text(value)
            analysis.setResult(value)
            analysis.reindexObject()
            updated_analyses.append(analysis)
            updated.append({
                "analysis_keyword": target_keyword,
                "value": value,
                "analysis_title": api.get_title(analysis),
            })

    if attachment_file and updated_analyses:
        for analysis in updated_analyses:
            attachment, error = _attach_to_worksheet_row(
                analysis,
                attachment_file,
                attachment_cache,
                attachment_title,
            )
            if attachment is None:
                continue
            ws = analysis.getWorksheet()
            details["worksheet_attachments"].append({
                "worksheet_uid": api.get_uid(ws) if ws else u"",
                "worksheet_title": api.get_title(ws) if ws else u"",
                "attachment_uid": api.get_uid(attachment),
                "attachment_title": api.get_title(attachment),
                "analysis_keyword": _ensure_text(analysis.getKeyword()),
            })

    if updated and (missing or skipped):
        details["message"] = u"Partial write completed"
        details["status"] = "partial"
    elif updated:
        details["message"] = u"Parsed results written successfully"
        details["status"] = "success"
    elif missing or skipped:
        details["message"] = u"No matching analyses were updated"
        details["status"] = "error"
    else:
        details["message"] = u"No assignments were applied"
        details["status"] = "noop"
    return details


def _write_parsed_results_to_sample(parsed, attachment_file=None, attachment_title=u""):
    """把解析后的 JSON 测试结果写回到系统分析结果中。"""
    if not isinstance(parsed, dict):
        return False, u"Parsed payload must be a JSON object", {}

    sample_payloads = parsed.get("samples") or []
    if not isinstance(sample_payloads, list) or not sample_payloads:
        return False, u"Parsed payload missing samples", {}

    attachment_cache = {}
    details = {
        "sample_count": len(sample_payloads),
        "processed_sample_count": 0,
        "updated_count": 0,
        "missing_count": 0,
        "skipped_count": 0,
        "samples": [],
        "updated": [],
        "missing": [],
        "skipped": [],
        "worksheet_attachments": [],
    }

    success_count = 0
    partial_count = 0
    noop_count = 0
    error_count = 0
    for sample_payload in sample_payloads:
        if isinstance(sample_payload, dict):
            sample_payload["_attachment_file"] = attachment_file
            sample_payload["_attachment_cache"] = attachment_cache
            sample_payload["_attachment_title"] = attachment_title
        sample_details = _write_sample_payload(sample_payload)
        details["samples"].append(sample_details)
        details["updated"].extend(sample_details.get("updated") or [])
        details["missing"].extend(sample_details.get("missing") or [])
        details["skipped"].extend(sample_details.get("skipped") or [])
        details["worksheet_attachments"].extend(sample_details.get("worksheet_attachments") or [])
        details["updated_count"] += len(sample_details.get("updated") or [])
        details["missing_count"] += len(sample_details.get("missing") or [])
        details["skipped_count"] += len(sample_details.get("skipped") or [])

        status = sample_details.get("status")
        if status in ("success", "partial"):
            details["processed_sample_count"] += 1
        if status == "success":
            success_count += 1
        elif status == "partial":
            partial_count += 1
        elif status == "noop":
            noop_count += 1
        else:
            error_count += 1

    message_parts = []
    if success_count:
        message_parts.append(u"success={}".format(success_count))
    if partial_count:
        message_parts.append(u"partial={}".format(partial_count))
    if noop_count:
        message_parts.append(u"noop={}".format(noop_count))
    if error_count:
        message_parts.append(u"error={}".format(error_count))
    summary_suffix = u", ".join(message_parts)

    if success_count and not partial_count and not error_count:
        message = u"Parsed results written successfully"
        if summary_suffix:
            message = u"{} ({})".format(message, summary_suffix)
        return True, message, details

    if success_count or partial_count:
        message = u"Partial write completed"
        if summary_suffix:
            message = u"{} ({})".format(message, summary_suffix)
        return True, message, details

    if noop_count and not error_count:
        message = u"No assignments were written"
        if summary_suffix:
            message = u"{} ({})".format(message, summary_suffix)
        return False, message, details

    message = u"No matching analyses were updated"
    if summary_suffix:
        message = u"{} ({})".format(message, summary_suffix)
    return False, message, details


def _server_loop(server_socket, data_forwarder):
    global _SERVER_STATUS, _MESSAGE_QUEUE, _SERVER_SOCKET, _JS_SOURCE
    
    try:
        _MESSAGE_QUEUE.put({
            "type": "system",
            "data": "Server listening on {}:{}".format(
                _SERVER_STATUS.get("host"), _SERVER_STATUS.get("port")
            )
        })

        inputs = [server_socket]

        while not _STOP_EVENT.is_set():
            try:
                readable, _, exceptional = select.select(inputs, [], inputs, 1.0)
            except Exception:
                break

            for s in readable:
                if s is server_socket:
                    try:
                        client_socket, client_address = s.accept()
                        client_socket.setblocking(0)
                        inputs.append(client_socket)
                        _MESSAGE_QUEUE.put({
                            "type": "system",
                            "data": "Client connected: {}".format(client_address)
                        })
                    except Exception:
                        continue
                else:
                    try:
                        data = s.recv(4096)
                        if data:
                            raw_text = _ensure_text(data)
                            parsed = _run_js_parser(_JS_SOURCE, raw_text)
                            
                            # HTTP 转发数据，使用同步转发确保结果可控。
                            forward_result = None
                            if data_forwarder and data_forwarder.is_enabled():
                                try:
                                    forward_success, forward_msg = data_forwarder.forward(raw_text, parsed)
                                    last_result = data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {}
                                    _SERVER_STATUS["last_forward_success"] = last_result.get("success")
                                    _SERVER_STATUS["last_forward_message"] = last_result.get("message") or forward_msg
                                    _SERVER_STATUS["last_forward_attempts"] = last_result.get("attempts") or 0
                                    _SERVER_STATUS["last_forward_status_code"] = last_result.get("status_code")
                                    forward_result = {
                                        "success": forward_success,
                                        "message": forward_msg,
                                        "attempts": _SERVER_STATUS["last_forward_attempts"],
                                        "status_code": _SERVER_STATUS["last_forward_status_code"],
                                    }
                                except Exception as e:
                                    _SERVER_STATUS["last_forward_success"] = False
                                    _SERVER_STATUS["last_forward_message"] = "Forward error: %s" % str(e)
                                    _SERVER_STATUS["last_forward_attempts"] = 0
                                    _SERVER_STATUS["last_forward_status_code"] = None
                                    forward_result = {
                                        "success": False,
                                        "message": "Forward error: %s" % str(e),
                                        "attempts": 0,
                                        "status_code": None,
                                    }
                            
                            _MESSAGE_QUEUE.put({
                                "type": "data",
                                "raw": raw_text,
                                "parsed": parsed,
                                "ts": int(time.time()),
                                "forward": forward_result,
                            })
                        else:
                            _MESSAGE_QUEUE.put({"type": "system", "data": "Client disconnected"})
                            inputs.remove(s)
                            s.close()
                    except socket.error:
                        if s in inputs:
                            inputs.remove(s)
                        s.close()

            for s in exceptional:
                if s in inputs:
                    inputs.remove(s)
                try:
                    s.close()
                except Exception:
                    pass

    except Exception as e:
        _SERVER_STATUS["error"] = str(e)
        _MESSAGE_QUEUE.put({"type": "error", "data": "Server error: {}".format(e)})
    finally:
        try:
            for s in list(locals().get("inputs", [])):
                try:
                    s.close()
                except Exception:
                    pass
        except Exception:
            pass
        _SERVER_SOCKET = None
        _SERVER_STATUS["running"] = False
        _MESSAGE_QUEUE.put({"type": "system", "data": "Server stopped"})


class InstrumentAcquisitionTestView(BrowserView):
    template = ViewPageTemplateFile("instrument_acquisition_test.pt")

    def __call__(self):
        return self.template()

    def templates(self):
        results = api.search({
            "portal_type": "InstrumentParsingTemplate",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }, catalog="senaite_catalog_setup")
        items = []
        for brain in results:
            try:
                items.append({
                    "uid": brain.UID,
                    "title": brain.Title,
                })
            except Exception:
                pass
        return items


class InstrumentAcquisitionPDFTestView(InstrumentAcquisitionTestView):
    template = ViewPageTemplateFile("instrument_acquisition_pdf_test.pt")


class InstrumentAcquisitionPDFExtract(BrowserView):
    def __call__(self):
        alsoProvides(self.request, IDisableCSRFProtection)
        upload = self.request.form.get("pdf_file")
        success, message, text, filename = _extract_pdf_text(upload)
        return _json_response(self.request, {
            "success": success,
            "message": message,
            "filename": filename,
            "text": text,
        })


class InstrumentAcquisitionPDFParse(BrowserView):
    def __call__(self):
        alsoProvides(self.request, IDisableCSRFProtection)

        uid = self.request.get("uid")
        template = _get_template_by_uid(uid)
        if template is None:
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template",
                "parsed": u"",
            })

        text = _ensure_text(self.request.get("text", u""))
        if not text:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing extracted text",
                "parsed": u"",
            })

        js_source = _get_js_source(template)
        parsed = _run_js_parser(js_source, text)
        return _json_response(self.request, {
            "success": True,
            "message": "Text parsed with template script",
            "parsed": parsed,
            "template_title": api.get_title(template),
        })


class InstrumentAcquisitionPDFWrite(BrowserView):
    def __call__(self):
        alsoProvides(self.request, IDisableCSRFProtection)

        parsed_text = _ensure_text(self.request.get("parsed", u""))
        if not parsed_text:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing parsed JSON text",
            })

        pdf_file = self.request.form.get("pdf_file") or self.request.get("pdf_file")
        pdf_filename = _ensure_text(getattr(pdf_file, "filename", "")) if pdf_file else u""

        try:
            parsed = json.loads(parsed_text)
        except Exception as exc:
            return _json_response(self.request, {
                "success": False,
                "message": u"Parsed JSON is invalid: {}".format(_ensure_text(exc)),
            })

        success, message, details = _write_parsed_results_to_sample(
            parsed,
            attachment_file=pdf_file,
            attachment_title=pdf_filename or u"Instrument report",
        )
        return _json_response(self.request, {
            "success": success,
            "message": message,
            "details": details,
        })


class InstrumentAcquisitionDebugView(BrowserView):
    template = ViewPageTemplateFile("instrument_acquisition_debug.pt")

    def __call__(self):
        return self.template()

    def get_template(self):
        uid = self.request.get("uid")
        if not uid and api.get_portal_type(self.context) == "InstrumentParsingTemplate":
            uid = api.get_uid(self.context)
        return _get_template_by_uid(uid)

    def get_host(self):
        template = self.get_template()
        return getattr(template, "ip_address", "") if template else ""

    def get_port(self):
        template = self.get_template()
        return getattr(template, "port", "") if template else ""


class InstrumentAcquisitionDebugStart(BrowserView):
    def __call__(self):
        global _SERVER_THREAD, _SERVER_STATUS, _SERVER_SOCKET, _JS_SOURCE
        alsoProvides(self.request, IDisableCSRFProtection)

        if _SERVER_STATUS["running"]:
            return _json_response(self.request, {"success": False, "message": "Server already running"})

        uid = self.request.get("uid")
        template = _get_template_by_uid(uid)
        if template is None:
            return _json_response(self.request, {"success": False, "message": "Invalid template"})

        host = getattr(template, "ip_address", "") or "0.0.0.0"
        port = getattr(template, "port", None)
        try:
            port = int(port)
        except Exception:
            return _json_response(self.request, {"success": False, "message": "Invalid port"})

        script_file = getattr(template, "script_file", None)
        script_filename = _ensure_text(getattr(script_file, "filename", "")) if script_file else ""
        js_source = _get_js_source(template)
        script_size = len(js_source) if js_source else 0
        _JS_SOURCE = js_source

        # 鑾峰彇HTTP杞彂閰嶇疆
        forward_enabled = getattr(template, "forward_enabled", False)
        forward_url = getattr(template, "forward_url", "") if forward_enabled else None

        _STOP_EVENT.clear()
        _SERVER_STATUS["host"] = host
        _SERVER_STATUS["port"] = port
        _SERVER_STATUS["template_uid"] = api.get_uid(template)
        _SERVER_STATUS["error"] = None
        _SERVER_STATUS["js_engine"] = _find_node()
        _SERVER_STATUS["script_filename"] = script_filename or None
        _SERVER_STATUS["script_size"] = script_size
        _SERVER_STATUS["forward_enabled"] = forward_enabled
        _SERVER_STATUS["forward_url"] = forward_url
        _SERVER_STATUS["last_forward_success"] = None
        _SERVER_STATUS["last_forward_message"] = ""
        _SERVER_STATUS["last_forward_attempts"] = 0
        _SERVER_STATUS["last_forward_status_code"] = None

        try:
            while True:
                _MESSAGE_QUEUE.get_nowait()
        except Queue.Empty:
            pass

        # 在主线程中初始化转发器，这样能正确获取 portal 对象。
        data_forwarder = None
        if forward_enabled:
            try:
                template_uid = api.get_uid(template)
                data_forwarder = forwarder.get_forwarder(template_uid)
                if data_forwarder:
                    startup_forward_msg = "Forwarder initialized"
                else:
                    startup_forward_msg = "Forwarder initialization failed"
            except Exception as e:
                startup_forward_msg = "Forwarder init error: %s" % str(e)
                data_forwarder = None

        # 鏋勫缓鍚姩淇℃伅
        startup_info = "JS engine: {} | script: {} ({} bytes)".format(
            _SERVER_STATUS["js_engine"] or "not found",
            _SERVER_STATUS["script_filename"] or "none",
            _SERVER_STATUS["script_size"] or 0,
        )
        if forward_enabled and forward_url:
            startup_info += " | HTTP forward: {}".format(forward_url)
        if data_forwarder:
            startup_info += " | {}".format(startup_forward_msg)
        
        _MESSAGE_QUEUE.put({
            "type": "system",
            "data": startup_info,
        })

        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((host, port))
            server_socket.listen(5)
            server_socket.setblocking(0)
        except Exception as e:
            try:
                server_socket.close()
            except Exception:
                pass
            _SERVER_STATUS["error"] = str(e)
            _SERVER_STATUS["running"] = False
            return _json_response(self.request, {"success": False, "message": str(e)})

        _SERVER_SOCKET = server_socket
        _SERVER_THREAD = threading.Thread(target=_server_loop, args=(server_socket, data_forwarder,))
        _SERVER_THREAD.daemon = True
        _SERVER_THREAD.start()
        _SERVER_STATUS["running"] = True
        return _json_response(self.request, {"success": True, "message": "Server started"})


class InstrumentAcquisitionDebugStop(BrowserView):
    def __call__(self):
        global _SERVER_SOCKET, _JS_SOURCE
        alsoProvides(self.request, IDisableCSRFProtection)

        if not _SERVER_STATUS["running"]:
            return _json_response(self.request, {"success": False, "message": "Server not running"})

        _STOP_EVENT.set()
        if _SERVER_SOCKET is not None:
            try:
                _SERVER_SOCKET.close()
            except Exception:
                pass
            _SERVER_SOCKET = None
        _JS_SOURCE = None
        _SERVER_STATUS["running"] = False
        return _json_response(self.request, {"success": True, "message": "Server stopping"})


class InstrumentAcquisitionDebugStatus(BrowserView):
    def __call__(self):
        return _json_response(self.request, _SERVER_STATUS)


class InstrumentAcquisitionDebugMessages(BrowserView):
    def __call__(self):
        messages = []
        try:
            while True:
                msg = _MESSAGE_QUEUE.get_nowait()
                messages.append(msg)
        except Queue.Empty:
            pass

        return _json_response(self.request, {
            "messages": messages,
            "status": "running" if _SERVER_STATUS["running"] else "stopped",
            "error": _SERVER_STATUS.get("error"),
        })

