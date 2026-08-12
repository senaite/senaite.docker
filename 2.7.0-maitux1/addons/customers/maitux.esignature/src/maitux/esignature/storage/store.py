# -*- coding: utf-8 -*-
"""Lightweight storage primitives for future Signature Record persistence."""

from datetime import datetime
from uuid import uuid4

from BTrees.OOBTree import OOBTree
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping
from zope.annotation.interfaces import IAnnotations


STORE_KEY = "maitux.esignature.store"


class SignatureRecordStore(object):
    """Portal-level lightweight store used by the MVP."""

    def __init__(self, context):
        self.context = context

    def _root(self):
        annotations = IAnnotations(self.context)
        root = annotations.get(STORE_KEY)
        if root is None:
            root = PersistentMapping()
            root["records"] = OOBTree()
            root["by_object_uid"] = OOBTree()
            root["pending_countersigns"] = OOBTree()
            annotations[STORE_KEY] = root
        elif "pending_countersigns" not in root:
            root["pending_countersigns"] = OOBTree()
        return root

    def records(self):
        return self._root()["records"]

    def object_index(self):
        return self._root()["by_object_uid"]

    def pending_countersigns(self):
        return self._root()["pending_countersigns"]

    def _pending_key(self, object_uid, transition_id):
        return "{}::{}".format(object_uid, transition_id)

    def get(self, signature_id, default=None):
        return self.records().get(signature_id, default)

    def list_for_object(self, object_uid):
        signature_ids = list(self.object_index().get(object_uid, []))
        return [self.records()[signature_id] for signature_id in signature_ids if signature_id in self.records()]

    def save(self, record):
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        data = dict(record)
        signature_id = data.get("signature_id") or uuid4().hex
        object_uid = data.get("object_uid")
        if not object_uid:
            raise ValueError("object_uid is required")

        data.setdefault("signature_id", signature_id)
        data.setdefault("status", "created")
        data.setdefault("created_at", datetime.utcnow().isoformat() + "Z")

        stored = PersistentMapping(data)
        self.records()[signature_id] = stored

        object_index = self.object_index()
        signature_ids = object_index.get(object_uid)
        if signature_ids is None:
            signature_ids = PersistentList()
            object_index[object_uid] = signature_ids
        if signature_id not in signature_ids:
            signature_ids.append(signature_id)

        return stored

    def get_pending_countersign(self, object_uid, transition_id, default=None):
        key = self._pending_key(object_uid, transition_id)
        return self.pending_countersigns().get(key, default)

    def save_pending_countersign(self, record):
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        data = dict(record)
        object_uid = data.get("object_uid")
        transition_id = data.get("transition_id")
        if not object_uid:
            raise ValueError("object_uid is required")
        if not transition_id:
            raise ValueError("transition_id is required")

        data.setdefault("status", "pending_countersign")
        data.setdefault("created_at", datetime.utcnow().isoformat() + "Z")
        stored = PersistentMapping(data)
        key = self._pending_key(object_uid, transition_id)
        self.pending_countersigns()[key] = stored
        return stored

    def delete_pending_countersign(self, object_uid, transition_id):
        key = self._pending_key(object_uid, transition_id)
        return self.pending_countersigns().pop(key, None)

