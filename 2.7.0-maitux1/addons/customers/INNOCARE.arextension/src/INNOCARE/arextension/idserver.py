# -*- coding: utf-8 -*-
"""ID Server variables adapter for Analysis Request.

URS-025 样品编号 = <部门简码><类型简码><YYMMDD><序号>，例如 BA260724001。
本适配器为 ID Server 提供 ``deptCode`` 变量（部门简码），取值：
    通过 AR 的检测项目（Analysis -> Department）关联到部门，
    取部门的 ``department_id``（Department ID）作为简码，
    未配置时回退到部门对象 ID（getId）。

模板配置（Setup -> ID Formatting，AnalysisRequest 行）：
    form:          {deptCode}{sampleType}{yymmdd}{seq:03d}
    sequence_type: generated
    split_length:  3
"""
from bika.lims.interfaces import IAnalysisRequest
from senaite.core.interfaces import IIdServerVariables
from zope.component import adapter
from zope.interface import implementer


@implementer(IIdServerVariables)
@adapter(IAnalysisRequest)
class ARIdServerVariables(object):
    """Provides extra ID Server variables for AnalysisRequest
    """

    def __init__(self, context):
        self.context = context

    def get_variables(self, **kw):
        return {
            "deptCode": self._get_department_code(),
        }

    def _get_department_code(self):
        """部门简码：取第一个关联部门（经检测项目 -> Department）。

        注意：不能走 getAnalyses()（目录查询）。AR 创建时先以临时 ID
        建对象，其分析子对象在编号生成（renameAfterCreation）时尚未写入
        senaite_catalog_analysis（临时对象被 CatalogMultiplexProcessor
        跳过索引），目录查询为空会导致部门取不到。直接遍历 AR 容器内的
        分析对象即可，与目录状态无关。
        """
        code = u""
        try:
            for analysis in self.context.objectValues(spec="Analysis"):
                department = analysis.getDepartment()
                if department is None:
                    continue
                getter = getattr(department, "getDepartmentID", None)
                if callable(getter):
                    code = getter() or u""
                if not code:
                    code = department.getId() or u""
                if code:
                    break
        except Exception:
            code = u""
        return code
