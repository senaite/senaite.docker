# -*- coding: utf-8 -*-

import json

from bika.lims import api
from senaite.core.exportimport.instruments import IInstrumentAutoImportInterface
from senaite.core.exportimport.instruments import IInstrumentImportInterface
from senaite.core.exportimport.instruments.logger import Logger
from zope.interface import implementer

from maitux.instrument_acquisition.services import acquisition


class InstrumentAcquisitionFileParser(object):
    """自动导入场景下的最小文件包装器。"""

    def __init__(self, infile):
        self._infile = infile

    def getInputFile(self):
        return self._infile


@implementer(IInstrumentImportInterface, IInstrumentAutoImportInterface)
class InstrumentAcquisitionImporter(Logger):
    """把 maitux.instrument_acquisition 桥接到原生导入入口。"""

    title = "Instrument Acquisition PDF/JS"

    def __init__(self, context):
        Logger.__init__(self)
        self.context = context
        self.instrument = None
        self.parser = None

    def get_automatic_parser(self, infile):
        return InstrumentAcquisitionFileParser(infile)

    def get_automatic_importer(self, instrument, parser, **kw):
        importer = self.__class__(self.context)
        importer.instrument = instrument
        importer.parser = parser
        return importer

    def process(self):
        """自动导入入口：按仪器上关联的模板执行提取、解析和写回。"""
        if not api.is_object(self.instrument):
            self.err("Instrument not found")
            return False

        template = acquisition.get_template_from_instrument(self.instrument)
        if not api.is_object(template):
            self.err(
                "No Instrument Parsing Template linked to this Instrument"
            )
            return False

        upload = self.parser.getInputFile() if self.parser else None
        if upload is None:
            self.err("No file selected")
            return False

        success, message, payload = acquisition.parse_and_write_report(
            template,
            upload,
        )
        filename = payload.get("filename") or getattr(upload, "filename", "")
        template_title = api.get_title(template)

        if success:
            # 记录模板和文件名，便于从 auto import log 追踪实际桥接链路。
            self.log(
                u"Imported '{}' with template '{}'".format(
                    filename,
                    template_title,
                )
            )
            self.log(message)
            return True

        self.err(
            u"Failed to import '{}' with template '{}'".format(
                filename,
                template_title,
            )
        )
        self.err(message)
        parsed_text = payload.get("parsed_text")
        if parsed_text:
            self.warn(parsed_text)
        return False

    def Import(self, context, request):
        """手工导入入口：复用与 auto_import_results 相同的后端逻辑。"""
        infile = request.form.get("instrument_results_file")
        instrument_uid = request.form.get("instrument", None)

        if not infile:
            return json.dumps({
                "errors": ["No file selected"],
                "log": [],
                "warns": [],
            })

        instrument = api.get_object(instrument_uid, None)
        importer = self.get_automatic_importer(
            instrument,
            self.get_automatic_parser(infile),
        )
        importer.process()

        return json.dumps({
            "errors": importer.errors,
            "log": importer.logs,
            "warns": importer.warns,
        })

