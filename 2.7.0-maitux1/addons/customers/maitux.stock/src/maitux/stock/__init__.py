from zope.i18nmessageid import MessageFactory

from maitux.stock.patches import patch_allowed_transitions_for_many

stockMessageFactory = MessageFactory('maitux.stock')
patch_allowed_transitions_for_many()

def initialize(context):
    """Initializer called when used as a Zope 2 product."""
    from maitux.stock import content
    content.initialize(context)

