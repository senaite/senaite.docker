# -*- coding: utf-8 -*-

from plone.supermodel import model
from senaite.core.interfaces import ISenaiteCore
from zope import schema
from zope.interface import Interface
from zope.publisher.interfaces.browser import IDefaultBrowserLayer

from maitux.hazardcategories import _
from maitux.hazardcategories.config import DEFAULT_CATEGORIES


class IMaituxHazardCategoriesLayer(ISenaiteCore, IDefaultBrowserLayer):
    pass


class IHazardCategories(Interface):
    """Marker interface for Hazard Categories container folder.
    """


class IHazardCategory(Interface):
    """Marker interface for a single Hazard Category item.
    """


class IHazardCategoriesSettings(model.Schema):

    categories = schema.Text(
        title=_(u"Hazard categories"),
        description=_(
            u"每行一条，格式为：CODE|Name|Common|pictogram-path 。"
            u"修改后立即生效，Reference Definition / Reference Sample "
            u"里的 Hazard categories 候选项会直接从这份配置读取。"
        ),
        default=DEFAULT_CATEGORIES,
        required=False,
    )

    categories_json = schema.Text(
        title=_(u"Hazard categories (JSON)"),
        description=_(
            u"按行存储的结构化 Hazard categories JSON 列表。"
            u"每行包含 uid/code/name/common/pictogram 字段。"
            u"由数据表维护界面自动生成，与 categories 文本字段双向同步。"
            u"不要手动修改此字段。"
        ),
        default=u"",
        required=False,
    )


class IHazardCategorySchema(model.Schema):
    """Schema for an individual Hazard Category item.
    """

    code = schema.TextLine(
        title=_(u"CODE"),
        description=_(u"Unique category code, e.g. GHS01, BIO01"),
        required=True,
    )

    name = schema.TextLine(
        title=_(u"Name (English)"),
        description=_(u"English name, e.g. Explosive"),
        required=False,
    )

    common = schema.TextLine(
        title=_(u"Common name / Chinese"),
        description=_(u"Common or localised name, e.g. explosive / 爆炸性"),
        required=False,
    )

    pictogram = schema.TextLine(
        title=_(u"Pictogram path"),
        description=_(u"Path relative to the portal, e.g. ghs/GHS01.svg or iso/W009.svg"),
        required=False,
    )

    usage_scope = schema.Choice(
        title=_(u"Usage scope"),
        description=_(
            u"Where this category should appear: Reference Definition only, "
            u"AR (Analysis Request / 请验单) only, or Both."
        ),
        vocabulary="maitux.hazardcategories.vocabularies.UsageScope",
        required=True,
        default=u"both",
    )
