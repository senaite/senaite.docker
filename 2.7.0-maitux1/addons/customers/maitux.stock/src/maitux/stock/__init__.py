from zope.i18nmessageid import MessageFactory

stockMessageFactory = MessageFactory('maitux.stock')
_ = stockMessageFactory

# NOTE: define the message factory *before* importing patches.
# patches -> browser.stockbatchactions -> browser/__init__ imports
# `from maitux.stock import _`; importing it first would raise
# "cannot import name _".
from maitux.stock.patches import patch_allowed_transitions_for_many

patch_allowed_transitions_for_many()

def initialize(context):
    """Initializer called when used as a Zope 2 product."""
    from maitux.stock import content
    content.initialize(context)

