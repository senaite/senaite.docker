from zope.interface import Interface

class IStockFolder(Interface):
    """Marker interface for Stock Folder
    """

class IStockItem(Interface):
    """Marker interface for Stock Items
    """


class IStock(Interface):
    """Marker interface for Stock
    """


class IStockManager(Interface):
    """Marker interface for Stock Manager
    """


class IStockSection(Interface):
    """Marker interface for Stock Section
    """


class IStockUnits(Interface):
    """Marker interface for Stock Units
    """


class IStockUnit(Interface):
    """Marker interface for Stock Unit
    """


class IStockTypes(Interface):
    """Marker interface for Stock Types
    """


class IStockType(Interface):
    """Marker interface for Stock Type
    """


class IStockPurchaseOrders(Interface):
    """Marker interface for Stock Purchase Orders
    """


class IStockPurchaseOrder(Interface):
    """Marker interface for Stock Purchase Order
    """


class IStockBatches(Interface):
    """Marker interface for Stock Batches
    """


class IStockBatch(Interface):
    """Marker interface for Stock Batch
    """
