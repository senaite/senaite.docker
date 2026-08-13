# -*- coding: utf-8 -*-

import json

from bika.lims import api

from maitux.instrument_acquisition.extender.instrument import FIELD_NAME
from maitux.instrument_acquisition.browser.deemo import instrument_acquisition_test


def get_template_from_instrument(instrument):
    """优先读取 Instrument 扩展字段，未配置时回退到旧的一对一模板关系。"""
    if not api.is_object(instrument):
        return None

    field = getattr(instrument, "getField", lambda *a, **k: None)(FIELD_NAME)
    if field is not None:
        try:
            template = field.get(instrument)
            if api.is_object(template):
                return template
        except Exception:
            pass

    # 兼容旧数据：如果模板对象上已经绑定了该仪器，
    # 也允许继续被桥接逻辑识别。
    brains = api.search({
        "portal_type": "InstrumentParsingTemplate",
        "sort_on": "sortable_title",
        "sort_order": "ascending",
    }, catalog="senaite_catalog_setup")
    instrument_uid = api.get_uid(instrument)
    for brain in brains:
        try:
            template = api.get_object(brain)
            linked_instrument = getattr(template, "getInstrument", lambda: None)()
            if api.is_object(linked_instrument) and api.get_uid(linked_instrument) == instrument_uid:
                return template
        except Exception:
            continue
    return None


def parse_and_write_report(template, upload):
    """复用现有测试页的提取、解析、写回逻辑，供手工导入和自动导入共用。"""
    success, message, text, filename = instrument_acquisition_test._extract_pdf_text(upload)
    if not success:
        return False, message, {
            "filename": filename,
            "extracted_text": text,
            "parsed_text": u"",
            "details": {},
        }

    js_source = instrument_acquisition_test._get_js_source(template)
    parsed_text = instrument_acquisition_test._run_js_parser(js_source, text)

    try:
        parsed = json.loads(parsed_text)
    except Exception as exc:
        return False, u"Parser output is invalid JSON: {}".format(
            instrument_acquisition_test._ensure_text(exc)
        ), {
            "filename": filename,
            "extracted_text": text,
            "parsed_text": parsed_text,
            "details": {},
        }

    success, message, details = instrument_acquisition_test._write_parsed_results_to_sample(
        parsed,
        attachment_file=upload,
        attachment_title=filename or u"Instrument report",
    )
    return success, message, {
        "filename": filename,
        "extracted_text": text,
        "parsed_text": parsed_text,
        "details": details,
    }

