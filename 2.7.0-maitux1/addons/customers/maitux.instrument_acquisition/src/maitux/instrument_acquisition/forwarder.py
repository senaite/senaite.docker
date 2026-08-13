# -*- coding: utf-8 -*-
import json
import logging
import threading
import time
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

from bika.lims import api

logger = logging.getLogger("maitux.instrument_acquisition")


class DataForwarder(object):
    """仪器数据 HTTP 转发器。"""

    MAX_RETRIES = 3
    RETRY_DELAY = 1

    def __init__(self, template):
        self.template = template
        self.forward_enabled = False
        self.forward_url = ""
        self.forward_method = "POST"
        self.forward_headers = ""
        self.forward_timeout = 30
        self._forward_history = []
        self._last_result = {
            "success": None,
            "message": "",
            "attempts": 0,
            "status_code": None,
            "timestamp": None,
        }
        
        if template and api.is_object(template):
            self.forward_enabled = getattr(template, "forward_enabled", False)
            self.forward_url = getattr(template, "forward_url", "")
            method = getattr(template, "forward_method", "POST")
            self.forward_method = method.upper() if method else "POST"
            self.forward_headers = getattr(template, "forward_headers", "")
            self.forward_timeout = getattr(template, "forward_timeout", 30)

    def is_enabled(self):
        """检查转发是否已启用。"""
        if not self.forward_enabled:
            return False
        if not self.forward_url:
            logger.warning("HTTP 转发已启用但未配置 URL")
            return False
        if requests is None:
            logger.error("缺少 requests 依赖，无法进行 HTTP 转发")
            return False
        return True

    def _parse_headers(self):
        """解析 HTTP 头配置。"""
        headers = {"Content-Type": "application/json"}
        if self.forward_headers:
            try:
                custom_headers = json.loads(self.forward_headers)
                if isinstance(custom_headers, dict):
                    headers.update(custom_headers)
            except Exception as e:
                logger.error("解析 HTTP 头配置失败: %s", e)
        return headers

    def _build_payload(self, raw_data, parsed_data, template_uid=None):
        """构建转发数据载荷，兼容 Python 2.7 编码。"""
        
        def safe_str(value):
            """安全转换为字符串，避免 Unicode 问题。"""
            if value is None:
                return None
            try:
                if isinstance(value, str):
                    return value
                if isinstance(value, unicode):
                    return value.encode('utf-8')
                return str(value)
            except:
                try:
                    return repr(value)
                except:
                    return None

        payload = {
            "timestamp": datetime.now().isoformat(),
            "template_uid": template_uid,
            "template_title": None,
            "instrument_uid": None,
            "instrument_title": None,
            "raw_data": safe_str(raw_data),
            "parsed_data": parsed_data,
        }

        if self.template and api.is_object(self.template):
            try:
                if not template_uid:
                    payload["template_uid"] = api.get_uid(self.template)
                payload["template_title"] = safe_str(api.get_title(self.template))
                
                instrument = self.template.getInstrument()
                if instrument and api.is_object(instrument):
                    payload["instrument_uid"] = api.get_uid(instrument)
                    payload["instrument_title"] = safe_str(api.get_title(instrument))
            except Exception as e:
                logger.error("构建载荷时出错: %s", e)

        return payload

    def _perform_request(self, url, method, payload, timeout):
        if method == "POST":
            logger.info("发送 POST 请求...")
            return requests.post(
                url,
                json=payload,
                timeout=timeout,
            )
        elif method == "PUT":
            logger.info("发送 PUT 请求...")
            return requests.put(
                url,
                json=payload,
                timeout=timeout,
            )
        raise ValueError("不支持的 HTTP 方法: {}".format(method))

    def _update_last_result(self, success, message, attempts, status_code=None):
        self._last_result = {
            "success": success,
            "message": message,
            "attempts": attempts,
            "status_code": status_code,
            "timestamp": datetime.now().isoformat(),
        }

    def forward(self, raw_data, parsed_data):
        """转发数据到 HTTP 接口。"""
        if not self.is_enabled():
            return False, "转发未启用或配置不完整"

        try:
            url = self.forward_url.strip()
            method = self.forward_method
            headers = self._parse_headers()
            payload = self._build_payload(raw_data, parsed_data)
            timeout = self.forward_timeout

            logger.info("=" * 50)
            logger.info("开始转发数据")
            logger.info("URL: %s", url)
            logger.info("方法: %s", method)
            logger.info("请求头: %s", headers)
            logger.info("请求载荷: %s", payload)
            logger.info("=" * 50)
            last_error = None
            last_status_code = None

            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    logger.info("HTTP 转发尝试 %s/%s", attempt, self.MAX_RETRIES)
                    response = self._perform_request(url, method, payload, timeout)

                    logger.info("响应状态码: %s", response.status_code)
                    logger.info("响应头: %s", response.headers)
                    logger.info("响应内容: %s", response.text)

                    last_status_code = response.status_code
                    success = response.status_code in (200, 201, 202, 204)
                    base_message = "HTTP {} - {}".format(response.status_code, response.reason)
                    if success:
                        if attempt == 1:
                            message = base_message
                        else:
                            message = "{} (第 {} 次成功)".format(base_message, attempt)
                        history_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "url": url,
                            "method": method,
                            "success": True,
                            "status_code": response.status_code,
                            "message": message,
                            "attempts": attempt,
                        }
                        self._forward_history.append(history_entry)
                        self._update_last_result(True, message, attempt, response.status_code)
                        logger.info("数据转发成功: %s", message)
                        return True, message

                    last_error = "{} (尝试 {}/{})".format(base_message, attempt, self.MAX_RETRIES)
                    if attempt < self.MAX_RETRIES:
                        logger.warning("HTTP 转发失败，准备重试: %s", last_error)
                        time.sleep(self.RETRY_DELAY)
                    else:
                        logger.error("HTTP 转发失败，已重试 %s 次: %s", self.MAX_RETRIES, last_error)

                except requests.exceptions.Timeout:
                    last_error = "HTTP 请求超时 ({} 秒)".format(self.forward_timeout)
                    if attempt < self.MAX_RETRIES:
                        logger.warning("%s，准备重试 (%s/%s)", last_error, attempt, self.MAX_RETRIES)
                        time.sleep(self.RETRY_DELAY)
                    else:
                        logger.error("%s，已重试 %s 次仍失败", last_error, self.MAX_RETRIES)
                except requests.exceptions.ConnectionError as e:
                    last_error = "连接失败: {}".format(str(e))
                    if attempt < self.MAX_RETRIES:
                        logger.warning("%s，准备重试 (%s/%s)", last_error, attempt, self.MAX_RETRIES)
                        time.sleep(self.RETRY_DELAY)
                    else:
                        logger.error("%s，已重试 %s 次仍失败", last_error, self.MAX_RETRIES)
                except ValueError as e:
                    last_error = str(e)
                    logger.error(last_error)
                    break

            final_message = "{}；连续重试 {} 次失败".format(
                last_error or "HTTP 转发失败",
                self.MAX_RETRIES,
            )
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "url": url,
                "method": method,
                "success": False,
                "status_code": last_status_code,
                "message": final_message,
                "attempts": self.MAX_RETRIES,
            }
            self._forward_history.append(history_entry)
            self._update_last_result(False, final_message, self.MAX_RETRIES, last_status_code)
            return False, final_message

        except Exception as e:
            error_msg = "转发异常: {}".format(str(e))
            logger.error(error_msg, exc_info=True)
            self._update_last_result(False, error_msg, 0, None)
            return False, error_msg

    def get_forward_history(self, limit=10):
        """获取转发历史记录。"""
        return self._forward_history[-limit:]

    def get_last_result(self):
        """获取最近一次转发结果。"""
        return dict(self._last_result)

    def clear_history(self):
        """清空转发历史。"""
        self._forward_history = []
        self._last_result = {
            "success": None,
            "message": "",
            "attempts": 0,
            "status_code": None,
            "timestamp": None,
        }


class AsyncDataForwarder(DataForwarder):
    """异步数据转发器。"""

    def __init__(self, template):
        super(AsyncDataForwarder, self).__init__(template)
        self._queue = []
        self._worker_thread = None
        self._stop_event = threading.Event()

    def forward_async(self, raw_data, parsed_data):
        """异步转发数据。"""
        if not self.is_enabled():
            return False

        task = {
            "raw_data": raw_data,
            "parsed_data": parsed_data,
            "timestamp": time.time(),
        }
        self._queue.append(task)

        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._start_worker()

        return True

    def _start_worker(self):
        """启动工作线程。"""
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop)
        self._worker_thread.daemon = True
        self._worker_thread.start()
        logger.info("异步转发工作线程已启动")

    def _worker_loop(self):
        """工作线程循环。"""
        while not self._stop_event.is_set():
            if self._queue:
                task = self._queue.pop(0)
                self.forward(task["raw_data"], task["parsed_data"])
            else:
                time.sleep(0.5)

    def stop(self):
        """停止工作线程。"""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2)
        logger.info("异步转发工作线程已停止")

    def get_queue_size(self):
        """获取队列大小。"""
        return len(self._queue)


_forwarder_cache = {}


def get_forwarder(template_uid):
    """获取或创建转发器实例。"""
    if template_uid in _forwarder_cache:
        return _forwarder_cache[template_uid]

    try:
        template = api.get_object(template_uid)
        if template and api.is_object(template) and api.get_portal_type(template) == "InstrumentParsingTemplate":
            forwarder = AsyncDataForwarder(template)
            _forwarder_cache[template_uid] = forwarder
            return forwarder
    except Exception as e:
        logger.error("获取转发器失败: %s", e)

    return None


def clear_forwarder_cache():
    """清空转发器缓存。"""
    for uid, forwarder in _forwarder_cache.items():
        if hasattr(forwarder, "stop"):
            forwarder.stop()
    _forwarder_cache.clear()

