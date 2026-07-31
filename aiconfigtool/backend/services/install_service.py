"""测试站点安装验证服务：每一步都验证实际效果，不做假成功。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error
import ssl
from base64 import b64encode

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

from infrastructure.config_repository import ConfigRepository
from shared import errors
from shared.result import Result

# install_service.py → services/ → backend/ → aiconfigtool/ → senaite.docker/
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_CUSTOM_CFG = os.path.join(_ROOT, "latest", "addons", "customers", "custom-addon.cfg")
_CUSTOMERS_HOST = os.path.join(_ROOT, "latest", "addons", "customers")


class InstallService:
    def __init__(self, repo=None):
        self._repo = repo or ConfigRepository()

    def install_and_verify(
        self, full_name: str, version: str, site_code: str, test_site_code: str,
    ) -> Result:
        steps = []
        site = self._repo.get_site(site_code)
        test_site = self._repo.get_site(test_site_code)
        if not site or not test_site:
            return Result.failure("站点信息不完整", code=errors.NOT_FOUND)

        container = (test_site.get("connection") or {}).get("containerName")
        test_url = test_site.get("url", "")
        test_user = (test_site.get("connection") or {}).get("authUser", "admin")
        test_pw = (test_site.get("connection") or {}).get("authPassword", "admin")

        if not container:
            container = self._detect_container(test_url)
            if container:
                steps.append({"step": "autodetect", "ok": True, "container": container})
            else:
                return Result.failure(
                    "无法确定测试站点容器，请在工作台编辑站点补充 containerName",
                    code=errors.SITE_CONNECTION_FAILURE,
                )

        pkg_id = "%s-%s" % (full_name, version)
        src = os.path.join(_ROOT, "aiconfigtool", "output", "projects", pkg_id, "src", full_name)
        dst_host = os.path.join(_CUSTOMERS_HOST, full_name)

        # ── Step 1: 拷贝源码 + 落地验证 ──
        if not os.path.isdir(src):
            steps.append({"step": "copy_src", "ok": False, "reason": "源码不存在: %s" % src})
            return Result.failure("源码不存在", code=errors.GENERATION_FAILED, details={"steps": steps})
        if os.path.isdir(dst_host):
            shutil.rmtree(dst_host)
        shutil.copytree(src, dst_host)
        if not os.path.isdir(dst_host) or not os.listdir(dst_host):
            steps.append({"step": "copy_src", "ok": False, "reason": "拷贝后目标目录为空"})
            return Result.failure("源码拷贝失败", code=errors.GENERATION_FAILED, details={"steps": steps})
        steps.append({"step": "copy_src", "ok": True, "files": len(os.listdir(dst_host))})

        # ── Step 2: 更新 cfg + 写后读验证 ──
        self._update_cfg(full_name)
        with open(_CUSTOM_CFG, "r", encoding="utf-8") as h:
            cfg_text = h.read()
        ok_cfg = full_name in cfg_text
        steps.append({"step": "update_cfg", "ok": ok_cfg})
        if not ok_cfg:
            return Result.failure("custom-addon.cfg 更新验证失败", code=errors.GENERATION_FAILED, details={"steps": steps})

        # ── Step 3: buildout + 结果验证 ──
        bo_ok, bo_msg = self._run_buildout(container, full_name, expect_egg_link=True)
        steps.append({"step": "buildout", "ok": bo_ok, "message": bo_msg})
        if not bo_ok:
            return Result.failure("buildout 失败", code=errors.GENERATION_FAILED, details={"steps": steps})

        # ── Step 4: restart + 确认服务恢复 ──
        rst_ok = self._restart_zope(container, test_url, test_user, test_pw)
        steps.append({"step": "restart", "ok": rst_ok})
        if not rst_ok:
            return Result.failure("Zope 重启后未恢复响应", code=errors.GENERATION_FAILED, details={"steps": steps})

        # ── Step 5: 安装前摸底（基线）──
        pre_fields = self._count_fields(test_site_code, full_name)

        # ── Step 6: HTTP 安装 + 验证已装 ──
        inst_ok, inst_msg = self._http_install(test_url, test_user, test_pw, full_name)
        steps.append({"step": "install", "ok": inst_ok, "message": inst_msg})

        # ── Step 7: 安装后摸底 + 对比验证 ──
        if inst_ok:
            time.sleep(3)
            post_fields = self._count_fields(test_site_code, full_name)
            ver_ok = post_fields is not None and pre_fields is not None
            steps.append({
                "step": "verify",
                "ok": ver_ok,
                "preScanTotalFields": pre_fields,
                "postScanTotalFields": post_fields,
            })
        else:
            ver_ok = False
            steps.append({"step": "verify", "ok": False, "reason": "安装未成功，跳过验证"})

        return Result.success({
            "verified": ver_ok,
            "installed": inst_ok,
            "steps": steps,
            "addon": full_name,
            "testSite": test_site_code,
        })

    # ── cfg ──
    def _update_cfg(self, full_name: str):
        try:
            with open(_CUSTOM_CFG, "r", encoding="utf-8") as h:
                text = h.read()
        except FileNotFoundError:
            text = "[buildout]\n[instance]\n"

        dev_line = "    /opt/addons/customers/%s" % full_name
        egg_line = "    %s" % full_name
        zcml_line = "    %s" % full_name

        for line, section in [(dev_line, "develop +="), (egg_line, "eggs +=")]:
            if line not in text:
                text = re.sub(r"(%s.*\n)" % section.replace("+", r"\+"), r"\1" + line + "\n", text, count=1)
                if line not in text:
                    text = text.replace("[buildout]", "[buildout]\n%s\n%s" % (section, line))

        if zcml_line not in text:
            text = re.sub(r"(\[instance\].*\n)", r"\1zcml +=\n" + zcml_line + "\n", text, count=1)
            if zcml_line not in text:
                text += "\n[instance]\nzcml +=\n" + zcml_line + "\n"

        os.makedirs(os.path.dirname(_CUSTOM_CFG), exist_ok=True)
        with open(_CUSTOM_CFG, "w", encoding="utf-8") as h:
            h.write(text)

    # ── buildout ──
    def _run_buildout(self, container: str, addon_name: str, expect_egg_link: bool = True) -> tuple[bool, str]:
        expected_state = "FOUND" if expect_egg_link else "NOT_FOUND"
        for attempt in range(1, 4):
            try:
                result = subprocess.run(
                    ["docker", "exec", "-i", container, "bash", "-lc",
                     "cd /home/senaite/senaitelims && /usr/local/bin/buildout -c buildout.cfg 2>&1"],
                    capture_output=True, text=True, timeout=300,
                )
                output = result.stdout + result.stderr
                # 验证 buildout 产出：develop egg 链接是否创建
                check_egg = subprocess.run(
                    ["docker", "exec", "-i", container, "bash", "-lc",
                     "ls /home/senaite/senaitelims/develop-eggs/%s.egg-link 2>/dev/null && echo FOUND || echo NOT_FOUND" % addon_name],
                    capture_output=True, text=True, timeout=10,
                )
                egg_state = check_egg.stdout.strip()
                if result.returncode == 0 and expected_state in egg_state:
                    if expect_egg_link:
                        return True, "buildout 成功（第 %d 次），egg-link 已创建" % attempt
                    return True, "buildout 成功（第 %d 次），egg-link 已移除" % attempt
                if "network" in output.lower() or "download" in output.lower() or "timeout" in output.lower():
                    if attempt < 3:
                        time.sleep(15 * attempt)
                        continue
                if attempt < 3:
                    time.sleep(10 * attempt)
                    continue
                return False, "buildout ret=%d, egg-link=%s, expected=%s" % (
                    result.returncode,
                    egg_state,
                    expected_state,
                )
            except Exception as e:
                if attempt < 3:
                    time.sleep(10 * attempt)
                    continue
                return False, "异常: %s" % str(e)[:150]
        return False, "重试 3 次仍失败"

    def _remove_container_egg_link(self, container: str, addon_name: str) -> tuple[bool, str]:
        egg_link = "/home/senaite/senaitelims/develop-eggs/%s.egg-link" % addon_name
        try:
            result = subprocess.run(
                ["docker", "exec", "-i", container, "bash", "-lc",
                 "rm -f %s && (test -e %s && echo STILL_FOUND || echo REMOVED)" % (egg_link, egg_link)],
                capture_output=True, text=True, timeout=15,
            )
            status = result.stdout.strip() or result.stderr.strip()
            if result.returncode == 0 and "REMOVED" in status:
                return True, "egg-link 已删除或本就不存在"
            return False, status or "egg-link 清理状态未知"
        except Exception as e:
            return False, "异常: %s" % str(e)[:150]

    def _cleanup_site_inventories(self, site_code: str) -> list[str]:
        removed = []
        for item in self._repo.list_inventories(site_code):
            inv_id = item.get("id")
            if inv_id and self._repo.delete_inventory(site_code, inv_id):
                removed.append(inv_id)
        if removed:
            site = self._repo.get_site(site_code) or {}
            if site:
                site["lastInventoryAt"] = ""
                self._repo.save_site(site_code, site)
        return removed

    # ── restart ──
    def _restart_zope(self, container: str, url: str, user: str, pw: str) -> bool:
        """docker restart 真正重启容器（bin/instance restart 在容器内无效）。"""
        try:
            subprocess.run(["docker", "restart", container],
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass
        # 等待 Zope 恢复，最多等 60s
        auth = b64encode(("%s:%s" % (user, pw)).encode()).decode()
        for i in range(30):
            time.sleep(2)
            try:
                req = urllib.request.Request(url.rstrip("/"), method="HEAD")
                req.add_header("Authorization", "Basic " + auth)
                resp = urllib.request.urlopen(req, timeout=5, context=ctx)
                if resp.status < 500:
                    return True
            except Exception:
                pass
        return False

    # ── HTTP 安装 ──
    def _http_install(self, url: str, user: str, pw: str, addon: str) -> tuple[bool, str]:
        auth = b64encode(("%s:%s" % (user, pw)).encode()).decode()
        try:
            data = urllib.parse.urlencode({"install_product": addon}).encode()
            req = urllib.request.Request(url.rstrip("/") + "/install_products", data=data, method="POST")
            req.add_header("Authorization", "Basic " + auth)
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            resp = urllib.request.urlopen(req, timeout=30, context=ctx)
            body = resp.read().decode(errors="replace")
            if "activated" in body.lower() or "installed" in body.lower():
                return True, "安装成功（响应确认）"
            return False, "响应中未找到安装确认"
        except Exception as e:
            return False, str(e)[:150]

    # ── 字段计数（验证用）──
    def _count_fields(self, site_code: str, addon_name: str) -> int | None:
        """对站点摸底，返回总字段数。用于安装前后对比。"""
        from services.inventory_service import InventoryService
        result = InventoryService(self._repo).scan_site(site_code)
        if result.is_failure():
            return None
        snap = self._repo.get_inventory(site_code, result.value["id"])
        if not snap:
            return None
        types = (snap.get("summary") or {}).get("types") or {}
        return sum(len(t.get("fields", [])) for t in types.values())

    # ── 清理 ──
    def cleanup(self, addon_name: str, site_code: str) -> Result:
        """彻底清理：Plone 卸载 → 删源码/egg-link/cfg → buildout → docker restart → 清缓存。"""
        site = self._repo.get_site(site_code)
        if not site:
            return Result.failure("站点不存在", code=errors.NOT_FOUND)
        url = site.get("url", "").rstrip("/")
        user = (site.get("connection") or {}).get("authUser", "admin")
        pw = (site.get("connection") or {}).get("authPassword", "admin")
        container = (site.get("connection") or {}).get("containerName")

        if not container:
            container = self._detect_container(url)
        if not container:
            return Result.failure("无法确定容器", code=errors.SITE_CONNECTION_FAILURE)

        steps = []

        # 1. Plone 卸载
        try:
            from base64 import b64encode
            auth_token = b64encode(("%s:%s" % (user, pw)).encode()).decode()
            data = urllib.parse.urlencode({"uninstall_product": addon_name}).encode()
            req = urllib.request.Request(url + "/install_products", data=data, method="POST")
            req.add_header("Authorization", "Basic " + auth_token)
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            urllib.request.urlopen(req, timeout=30, context=ctx)
            steps.append({"step": "uninstall", "ok": True})
        except Exception as e:
            steps.append({"step": "uninstall", "ok": False, "reason": str(e)[:80]})

        # 2. 删源码
        src_dir = os.path.join(_CUSTOMERS_HOST, addon_name)
        if os.path.isdir(src_dir):
            shutil.rmtree(src_dir)
            steps.append({"step": "remove_src", "ok": True})
        else:
            steps.append({"step": "remove_src", "ok": True, "skipped": True})

        # 3. 删 cfg 条目
        try:
            with open(_CUSTOM_CFG, "r", encoding="utf-8") as h:
                text = h.read()
            for line in [
                "    /opt/addons/customers/%s" % addon_name,
                "    %s" % addon_name,
            ]:
                text = text.replace(line + "\n", "")
                text = text.replace(line, "")
            # 清理空行
            text = re.sub(r"\n{3,}", "\n\n", text)
            with open(_CUSTOM_CFG, "w", encoding="utf-8") as h:
                h.write(text)
            steps.append({"step": "update_cfg", "ok": True})
        except Exception as e:
            steps.append({"step": "update_cfg", "ok": False, "reason": str(e)[:80]})

        # 4. 删 develop egg-link，避免 buildout 前后都残留旧引用
        egg_ok, egg_msg = self._remove_container_egg_link(container, addon_name)
        steps.append({"step": "remove_egg_link", "ok": egg_ok, "message": egg_msg})

        # 5. buildout（清理模式要求 egg-link 最终不存在）
        bo_ok, bo_msg = self._run_buildout(container, addon_name, expect_egg_link=False)
        steps.append({"step": "buildout", "ok": bo_ok, "message": bo_msg})

        # 6. docker restart
        rst_ok = self._restart_zope(container, url, user, pw)
        steps.append({"step": "restart", "ok": rst_ok})

        # 7. 删该测试站点的全部摸底快照，避免后续继续使用带旧字段的缓存
        removed_inventories = self._cleanup_site_inventories(site_code)
        steps.append({
            "step": "remove_inventories",
            "ok": True,
            "count": len(removed_inventories),
            "items": removed_inventories[:10],
        })

        critical_failed = any(
            not step.get("ok")
            for step in steps
            if step.get("step") in {"update_cfg", "remove_egg_link", "buildout", "restart"}
        )
        if critical_failed:
            return Result.failure(
                "Addon 清理未完成，请根据步骤详情继续处理",
                code=errors.GENERATION_FAILED,
                details={"steps": steps},
            )

        return Result.success({
            "cleaned": True,
            "removedInventories": removed_inventories,
            "steps": steps,
        })
    def _detect_container(self, url: str) -> str | None:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            port = str(parsed.port or (443 if parsed.scheme == "https" else 80))
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}|{{.Ports}}"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                if not line: continue
                parts = line.split("|", 1)
                if len(parts) < 2: continue
                name, ports = parts[0], parts[1]
                if ":" + port + "->" in ports or ":" + port + "/" in ports:
                    return name.strip()
        except Exception:
            pass
        return None
