"""站点资源 handler。"""

from __future__ import annotations

import json
import os

from infrastructure.config_repository import ConfigRepository
from shared import errors
from shared.result import Result

_repo = ConfigRepository()


def list_company_sites(params, **_):
    return Result.success(_repo.list_sites(params["code"]))


def get_site(params, **_):
    code = params["code"]
    site = _repo.get_site(code)
    if site is None:
        return Result.failure(
            "站点不存在: %s" % code,
            code=errors.NOT_FOUND,
            suggestion="确认站点代码是否正确",
        )
    return Result.success(site)


def create_site(params, body, **_):
    """新增站点：写到 data/sites/{code}/config.json。"""
    body = body or {}
    code = body.get("code")
    if not code:
        return Result.failure("缺少 code", code=errors.VALIDATION_ERROR)
    site_data = dict(body)
    _repo.save_site(code, site_data)
    return Result.success(site_data)


def test_connection(params, **_):
    """连接测试：对站点 URL 做一次 HTTP HEAD 检查。"""
    code = params["code"]
    site = _repo.get_site(code)
    if site is None:
        return Result.failure("站点不存在: %s" % code, code=errors.NOT_FOUND)
    url = site.get("url", "")
    if not url:
        return Result.failure("站点缺少 URL", code=errors.SITE_CONNECTION_FAILED)
    import urllib.request
    import urllib.error
    import ssl
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=10, context=ctx)
        return Result.success({"reachable": True, "url": url})
    except urllib.error.HTTPError as e:
        # 只要能返回 HTTP 状态码（如 401 Unauthorized 等），说明服务是可达的
        return Result.success({"reachable": True, "url": url, "note": str(e)})
    except Exception as e:
        return Result.success({"reachable": False, "url": url, "reason": str(e)})


def list_site_inventories(params, **_):
    return Result.success(_repo.list_inventories(params["code"]))


def get_inventory(params, **_):
    code = params["code"]
    inv_id = params["id"]
    if not _repo.get_site(code):
        return Result.failure("站点不存在: %s" % code, code=errors.NOT_FOUND)
    snapshot = _repo.get_inventory(code, inv_id)
    if snapshot is None:
        return Result.failure("摸底文件不存在: %s" % inv_id, code=errors.NOT_FOUND)
    return Result.success(snapshot)


def update_site(params, body, **_):
    code = params["code"]
    existing = _repo.get_site(code)
    if existing is None:
        return Result.failure("站点不存在: %s" % code, code=errors.NOT_FOUND)
    merged = dict(existing)
    if body:
        merged.update(body)
    _repo.save_site(code, merged)
    return Result.success(merged)


def delete_site(params, **_):
    code = params["code"]
    if _repo.get_site(code) is None:
        return Result.failure("站点不存在: %s" % code, code=errors.NOT_FOUND)
    _repo.delete_site(code)
    return Result.success(None)


def delete_inventory(params, **_):
    code = params["code"]
    inv_id = params["id"]
    if not _repo.get_site(code):
        return Result.failure("站点不存在: %s" % code, code=errors.NOT_FOUND)
    if _repo.delete_inventory(code, inv_id):
        return Result.success(None)
    return Result.failure("摸底文件不存在: %s" % inv_id, code=errors.NOT_FOUND)


def register(router) -> None:
    router.get("/api/companies/{code}/sites", list_company_sites)
    router.post("/api/companies/{code}/sites", create_site)
    router.get("/api/sites/{code}", get_site)
    router.put("/api/sites/{code}", update_site)
    router.delete("/api/sites/{code}", delete_site)
    router.post("/api/sites/{code}/test-connection", test_connection)
    router.get("/api/sites/{code}/inventories", list_site_inventories)
    router.get("/api/sites/{code}/inventories/{id}", get_inventory)
    router.delete("/api/sites/{code}/inventories/{id}", delete_inventory)
