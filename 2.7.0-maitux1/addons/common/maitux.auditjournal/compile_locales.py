# -*- coding: utf-8 -*-
"""把本包 locales 下的 .po 编译成 .mo（宿主机 Python 3 运行，零依赖）。

为什么自己写：容器和宿主都没有 `msgfmt`，Python 也不提供可 import 的
msgfmt 模块。GNU 的 .mo 格式本身很简单，自己生成比引入新依赖划算。

用法（在本包目录下）：

    python compile_locales.py

改完 .po **必须重跑一次**，否则界面用的还是旧 .mo —— 这是个静默失效：
翻译不生效但不报任何错。
"""

import array
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOCALES = os.path.join(HERE, "src", "maitux", "auditjournal", "locales")

# 只解析我们自己写的简单 .po：msgid / msgstr，支持多行续接，忽略注释与 fuzzy
_TOKEN = re.compile(r'^(msgid|msgstr)\s+"(.*)"\s*$')
_CONT = re.compile(r'^"(.*)"\s*$')


def unescape(text):
    return (text.replace('\\n', '\n').replace('\\t', '\t')
                .replace('\\"', '"').replace('\\\\', '\\'))


def parse_po(path):
    entries = {}
    key = None
    current = {"msgid": None, "msgstr": None}
    last = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = _TOKEN.match(line.strip())
            if m:
                kind, value = m.group(1), unescape(m.group(2))
                if kind == "msgid":
                    # 上一条收尾
                    if current["msgid"] is not None and current["msgstr"]:
                        entries[current["msgid"]] = current["msgstr"]
                    current = {"msgid": value, "msgstr": None}
                else:
                    current["msgstr"] = value
                last = kind
                continue
            m = _CONT.match(line.strip())
            if m and last:
                current[last] = (current[last] or "") + unescape(m.group(1))
    if current["msgid"] is not None and current["msgstr"]:
        entries[current["msgid"]] = current["msgstr"]
    return entries


def write_mo(entries, path):
    """GNU .mo：magic + 索引表 + 字符串区。空 msgid 是元数据头，必须保留。"""
    keys = sorted(entries.keys())
    offsets, ids, strs = [], b"", b""
    for key in keys:
        value = entries[key]
        kb, vb = key.encode("utf-8"), value.encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\0"
        strs += vb + b"\0"

    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]

    output = struct.pack("Iiiiiii", 0x950412de, 0, len(keys),
                         7 * 4, 7 * 4 + len(keys) * 8, 0, 0)
    output += array.array("i", koffsets + voffsets).tobytes()
    output += ids + strs
    with open(path, "wb") as fh:
        fh.write(output)


def main():
    if not os.path.isdir(LOCALES):
        print("没有 locales 目录：%s" % LOCALES)
        return 2
    count = 0
    for root, _dirs, files in os.walk(LOCALES):
        for fn in files:
            if not fn.endswith(".po"):
                continue
            po = os.path.join(root, fn)
            mo = po[:-3] + ".mo"
            entries = parse_po(po)
            write_mo(entries, mo)
            translated = len([k for k in entries if k])
            print("%s -> %s（%d 条）"
                  % (os.path.relpath(po, HERE), os.path.basename(mo),
                     translated))
            count += 1
    if not count:
        print("没找到任何 .po")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
