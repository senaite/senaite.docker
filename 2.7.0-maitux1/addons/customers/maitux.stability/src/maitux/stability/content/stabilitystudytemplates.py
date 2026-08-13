# -*- coding: utf-8 -*-
from bika.lims.interfaces import IDoNotSupportSnapshots
from plone.supermodel import model
from senaite.core import logger
from senaite.core.content.base import Container
from senaite.core.interfaces import IHideActionsMenu
from zope.annotation.interfaces import IAnnotations
from zope.interface import implementer

from maitux.stability.interfaces import IStabilityPlanTemplates


class IStabilityPlanTemplatesSchema(model.Schema):
    pass


@implementer(
    IStabilityPlanTemplates,
    IStabilityPlanTemplatesSchema,
    IDoNotSupportSnapshots,
    IHideActionsMenu,
)
class StabilityPlanTemplates(Container):
    pass


try:
    from Products.CMFPlone.interfaces.constrains import IConstrainTypes
    from Products.CMFPlone.interfaces.constrains import ISelectableConstrainTypes
except Exception:
    IConstrainTypes = None
    ISelectableConstrainTypes = None


if ISelectableConstrainTypes is not None:

    @implementer(ISelectableConstrainTypes, IConstrainTypes)
    class StabilityPlanTemplatesConstrainTypes(object):
        def __init__(self, context):
            self.context = context

        def _anno(self):
            try:
                return IAnnotations(self.context)
            except Exception:
                return {}

        def _get_key(self, name):
            return "maitux.stability.constraints.%s" % name

        def _get_mode(self):
            anno = self._anno()
            return anno.get(self._get_key("mode"), 0)

        def _set_mode(self, value):
            if value not in (0, 1, 2):
                raise ValueError()
            anno = self._anno()
            anno[self._get_key("mode")] = value

        def _fti_allowed_types(self):
            try:
                from bika.lims import api
                types_tool = api.get_tool("portal_types")
                if not types_tool:
                    return []
                fti = types_tool.getTypeInfo(api.get_portal_type(self.context))
                if not fti:
                    return []
                if not getattr(fti, "filter_content_types", False):
                    return []
                allowed = getattr(fti, "allowed_content_types", ()) or ()
                return list(allowed)
            except Exception as exc:
                logger.warning("Could not determine allowed content types: %r", exc)
                return []

        def _type_infos(self, type_ids):
            try:
                from bika.lims import api
                types_tool = api.get_tool("portal_types")
            except Exception:
                types_tool = None
            if not types_tool:
                return []

            infos = []
            for type_id in type_ids or []:
                if not type_id:
                    continue
                try:
                    ti = types_tool.getTypeInfo(type_id)
                except Exception:
                    ti = None
                if ti is not None:
                    infos.append(ti)
            return infos

        def _validate_type_ids(self, type_ids):
            try:
                from bika.lims import api
                types_tool = api.get_tool("portal_types")
            except Exception:
                types_tool = None

            if not types_tool:
                raise ValueError("portal_types not available")

            allowed_by_fti = set(self._fti_allowed_types())
            for type_id in type_ids:
                if not type_id:
                    continue
                if types_tool.getTypeInfo(type_id) is None:
                    raise ValueError("%s is not a valid type id" % type_id)
                if allowed_by_fti and type_id not in allowed_by_fti:
                    raise ValueError("%s is not a valid type id" % type_id)

        def getConstrainTypesMode(self):
            return self._get_mode()

        def setConstrainTypesMode(self, mode):
            self._set_mode(mode)

        def getLocallyAllowedTypes(self):
            anno = self._anno()
            value = anno.get(self._get_key("locally_allowed"), None)
            if value in (None, [], ()):
                return []
            return list(value)

        def setLocallyAllowedTypes(self, types):
            types = list(types or [])
            self._validate_type_ids(types)
            anno = self._anno()
            anno[self._get_key("locally_allowed")] = tuple(types)

        def getImmediatelyAddableTypes(self):
            anno = self._anno()
            value = anno.get(self._get_key("immediately_addable"), None)
            if value in (None, [], ()):
                return []
            return list(value)

        def setImmediatelyAddableTypes(self, types):
            types = list(types or [])
            self._validate_type_ids(types)
            anno = self._anno()
            anno[self._get_key("immediately_addable")] = tuple(types)

        def listPossibleTypes(self):
            return self._fti_allowed_types()

        def getDefaultAddableTypes(self):
            return self._fti_allowed_types()

        def allowedContentTypes(self):
            possible = self._fti_allowed_types()
            mode = self.getConstrainTypesMode()
            if mode != 1:
                return self._type_infos(possible)

            local = self.getLocallyAllowedTypes() or []
            if not local:
                return self._type_infos(possible)
            possible_set = set(possible)
            return self._type_infos([t for t in local if t in possible_set])

        def immediatelyAddableTypes(self):
            allowed_infos = self.allowedContentTypes()
            mode = self.getConstrainTypesMode()
            if mode != 1:
                return allowed_infos

            addable = self.getImmediatelyAddableTypes() or []
            if not addable:
                return allowed_infos

            allowed_ids = [ti.getId() for ti in allowed_infos if hasattr(ti, "getId")]
            allowed_set = set(allowed_ids)
            return self._type_infos([t for t in addable if t in allowed_set])

        def isTypeAllowed(self, type_id):
            if not type_id:
                return False
            allowed_by_fti = set(self._fti_allowed_types())
            if allowed_by_fti and type_id not in allowed_by_fti:
                return False

            mode = self.getConstrainTypesMode()
            if mode != 1:
                return True

            local = set(self.getLocallyAllowedTypes() or [])
            if not local:
                return True
            return type_id in local

