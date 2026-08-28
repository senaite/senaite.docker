# -*- coding: utf-8 -*-
"""审核人指派权限

拆成两个而不是一个：rolemap 按角色全站授予，只给一个 permission 就意味着
任意 Analyst 能改任意工作表的审核人 —— Care 的 RestrictWorksheetUsersAccess=False
让 Analyst 能访问所有工作表，SENAITE 侧没有归属边界可用。

归属判据取 worksheet.getAnalyst()，与 SENAITE 自己的 guard_submit
（提交人必须是被指派分析员）同一套语义，且与「谁能创建工作表」无关 ——
严格实验室（LabManager 建表指派）和研发实验室（实验员自己建表）都成立。

两个常量都必须在 configure.zcml 里用 <permission id title> 注册，
否则 rolemap.xml 导入时 manage_permission 会报
"The permission ... is invalid"。
"""

# 给自己是分析员的工作表选审核人：实验员日常操作
AssignReviewer = "maitux.reviewerassignment: Assign Reviewer"

# 改别人的工作表：死结救场，仅高权限
ReassignAnyReviewer = "maitux.reviewerassignment: Reassign Any Reviewer"
