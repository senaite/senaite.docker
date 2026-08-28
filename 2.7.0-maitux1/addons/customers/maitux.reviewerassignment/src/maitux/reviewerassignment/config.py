# -*- coding: utf-8 -*-
"""模块配置常量"""

PROJECTNAME = "maitux.reviewerassignment"
ROOT_ID = "reviewerassignmentroot"
ROOT_TITLE = u"审核工作表"
WORKSHEET_REVIEWER_BEHAVIOR = "maitux.reviewerassignment.behavior.worksheetreviewer"
REVIEWER_FIELD = "reviewer_userid"
REVIEWER_INDEX = "getReviewerUserId"
VERIFIER_ROLE = "Verifier"


# 可修改审核人的工作表状态，与 senaite.core 的 edit_states 保持一致。
REVIEWER_EDIT_STATES = ("open", "to_be_verified")

# registry 记录前缀，与 IReviewerAssignmentControlPanelSettings 配套。
REGISTRY_PREFIX = "maitux.reviewerassignment"
