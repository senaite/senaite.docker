# -*- coding: utf-8 -*-
# MAITUX Calculation Enhancement Add-on

from maitux.calcenhance.patches import allow_locked_writes  # noqa: F401
from maitux.calcenhance.patches import apply_patches

# Apply monkey-patches on import
apply_patches()

# `allow_locked_writes` is re-exported for the instrument importer:
#
#     from maitux.calcenhance import allow_locked_writes
#     with allow_locked_writes():
#         analysis.setInterimValue(keyword, values)
#
# Outside that block, interims flagged "locked" in the Calculation config
# reject any write that would change an already captured value.
__all__ = ["apply_patches", "allow_locked_writes"]
