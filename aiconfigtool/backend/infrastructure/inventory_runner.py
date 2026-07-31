"""运行时摸底：调用目标 Senaite 站点的 @@maitux-runtime-inventory 端点，
拉取运行时能力清单（内容类型 + 字段 + 权限）。

已在本地 Senaite（Zope4/py2 镜像）验证：HTTP + Basic Auth 可用，容器内
脚本运行器（bin/instance run / zconsole）在该镜像 bootstrap 损坏，故走 HTTP。

零第三方依赖：仅用 urllib。
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.error
import urllib.request
from typing import Optional


def _site_base(base_url: str, site_id: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("base_url is required")
    site = (site_id or "").strip().strip("/")
    if not site:
        return base
    # base_url 可能已含 site_id（如 http://host/senaite），避免重复拼接
    if base.lower().endswith("/" + site.lower()):
        return base
    return base + "/" + site


class InventoryRunner:
    """通过 HTTP 拉取运行时摸底。

    用法：
        runner = InventoryRunner("http://127.0.0.1:8083", "senaite",
                                 username="admin", password="admin")
        raw = runner.fetch_runtime()          # 原始 529KB JSON
        summary = InventoryRunner.summarize(raw)   # Gate1 用的精简结构
    """

    ENDPOINT = "@@maitux-runtime-inventory"

    def __init__(
        self,
        base_url: str,
        site_id: str,
        username: str = "admin",
        password: str = "admin",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url
        self.site_id = site_id
        self.username = username
        self.password = password
        self.timeout = timeout_seconds

    def fetch_runtime(
        self,
        project_id: str = "AiConfigTool",
        schema_version: str = "0.1",
        phase: str = "phase1",
    ) -> dict:
        url = "%s/%s?%s" % (
            _site_base(self.base_url, self.site_id),
            self.ENDPOINT,
            urllib.parse.urlencode(
                {
                    "project_id": project_id,
                    "schema_version": schema_version,
                    "phase": phase,
                }
            ),
        )
        req = urllib.request.Request(url, method="GET")
        token = ("%s:%s" % (self.username, self.password)).encode("utf-8")
        req.add_header(
            "Authorization", "Basic " + base64.b64encode(token).decode("ascii")
        )
        
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
                content_type = (resp.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            content_type = (exc.headers.get("Content-Type") or "").lower()
            if exc.code in (401, 403):
                raise RuntimeError("站点认证失败，请配置正确的管理员账号密码")
            raise RuntimeError("端点请求失败: HTTP %s" % exc.code)

        payload_stripped = payload.lstrip()
        if "html" in content_type or payload_stripped.startswith("<"):
            if "Unauthorized" in payload:
                raise RuntimeError("站点认证失败，请配置正确的管理员账号密码")
            raise RuntimeError("端点返回 HTML 而不是 JSON，请确认代理转发和端点权限")

        try:
            return json.loads(payload)
        except ValueError:
            raise RuntimeError("端点返回了非 JSON 内容")

    # ── 精简为 Gate1 所需结构 ──
    @staticmethod
    def summarize(raw: dict) -> dict:
        """把原始摸底压成「类型 → 字段/框架」的精简结构，供冲突校验使用。

        返回：
            {
              "types": {
                 "AnalysisProfile": {
                     "title": "...", "framework": "dexterity",
                     "fields": [{"name","type","required"}...],
                     "behaviors": [...]
                 }, ...
              },
              "typeCount": 113
            }
        """
        types: dict[str, dict] = {}
        for ent in raw.get("entities") or []:
            if not isinstance(ent, dict):
                continue
            type_id = ent.get("type_id")
            if not type_id:
                continue
            fields = list(ent.get("dexterity_fields") or []) + list(
                ent.get("at_fields") or []
            )
            types[type_id] = {
                "title": ent.get("title", ""),
                "framework": ent.get("framework", "unknown"),
                "addPermission": ent.get("add_permission") or "",
                "fields": [
                    {
                        "name": f.get("name"),
                        "type": f.get("type"),
                        "required": bool(f.get("required")),
                    }
                    for f in fields
                    if isinstance(f, dict) and f.get("name")
                ],
                "behaviors": list(ent.get("behaviors") or []),
            }
        return {"types": types, "typeCount": len(types)}

    @staticmethod
    def field_names(summary: dict, type_id: str) -> set:
        """某类型现有字段名集合（冲突校验用）。"""
        t = (summary.get("types") or {}).get(type_id)
        if not t:
            return set()
        return {f["name"] for f in t.get("fields") or [] if f.get("name")}
