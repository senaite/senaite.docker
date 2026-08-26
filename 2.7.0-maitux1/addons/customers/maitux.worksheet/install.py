#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""Setup maitux.worksheet addon in the Zope interpreter after container restart.

Idempotent - safe to run multiple times. Graceful about missing paths.
"""
import os
import sys

SENAITE_ROOT = "/home/senaite/senaitelims"
SRC_PATH = os.path.join(SENAITE_ROOT, "src", "maitux.worksheet", "src")
INTERPRETER_PATH = os.path.join(SENAITE_ROOT, "parts", "instance", "bin", "interpreter")
EGG_LINK_PATH = os.path.join(SENAITE_ROOT, "develop-eggs", "maitux.worksheet.egg-link")
SLUGS_DIR = os.path.join(SENAITE_ROOT, "parts", "instance", "etc", "package-includes")


def ensure_dir(path):
    """Create directory if it doesn't exist."""
    if not os.path.exists(path):
        try:
            os.makedirs(path)
            print("Created directory:", path)
        except Exception as e:
            print("WARNING: could not create", path, "-", e)


def fix_interpreter():
    """Add maitux.worksheet to Zope interpreter's sys.path."""
    if not os.path.exists(INTERPRETER_PATH):
        print("Interpreter not found at", INTERPRETER_PATH, "- skipping.")
        return True

    with open(INTERPRETER_PATH, 'r') as f:
        content = f.read()

    if "maitux.worksheet" in content:
        print("Interpreter already has maitux.worksheet. Skipping.")
        return True

    insert_line = "  '{}',\n".format(SRC_PATH)
    old = "sys.path[0:0] = [\n"
    new = old + insert_line
    content = content.replace(old, new, 1)

    with open(INTERPRETER_PATH, 'w') as f:
        f.write(content)

    print("Interpreter updated with maitux.worksheet path.")
    return True


def create_egg_link():
    """Create egg-link for maitux.worksheet."""
    if os.path.exists(EGG_LINK_PATH):
        print("Egg-link already exists.")
        return True
    try:
        pkg_dir = os.path.join(SENAITE_ROOT, "src", "maitux.worksheet")
        ensure_dir(os.path.dirname(EGG_LINK_PATH))
        with open(EGG_LINK_PATH, 'w') as f:
            f.write(pkg_dir + "\n")
        print("Egg-link created at", pkg_dir)
        return True
    except Exception as e:
        print("ERROR creating egg-link:", e)
        return True


def create_zcml_slugs():
    """Create ZCML slugs so QuickInstaller can discover the addon."""
    ensure_dir(SLUGS_DIR)

    config_file = os.path.join(SLUGS_DIR, "100-maitux.worksheet-configure.zcml")
    if not os.path.exists(config_file):
        with open(config_file, "w") as f:
            f.write('<configure xmlns="http://namespaces.zope.org/zope">\n')
            f.write('  <include package="maitux.worksheet" />\n')
            f.write('</configure>\n')
        print("ZCML configure slug created.")

    overrides_file = os.path.join(SLUGS_DIR, "100-maitux.worksheet-overrides.zcml")
    if not os.path.exists(overrides_file):
        with open(overrides_file, "w") as f:
            f.write('<configure xmlns="http://namespaces.zope.org/zope">\n')
            f.write('  <include package="maitux.worksheet" file="overrides.zcml" />\n')
            f.write('</configure>\n')
        print("ZCML overrides slug created.")
    return True


if __name__ == "__main__":
    print("=== Setting up maitux.worksheet ===")
    fix_interpreter()
    create_egg_link()
    create_zcml_slugs()
    print("All setup steps completed.")
    # Never exit non-zero - entrypoint uses set -e
