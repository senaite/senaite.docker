from zope.i18nmessageid import MessageFactory


stabilityMessageFactory = MessageFactory("maitux.stability")


def initialize(context):
    """Initializer called when used as a Zope 2 product."""
    from maitux.stability import content
    content.initialize(context)

