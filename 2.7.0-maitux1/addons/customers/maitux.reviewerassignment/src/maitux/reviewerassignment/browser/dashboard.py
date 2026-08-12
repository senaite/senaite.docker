# -*- coding: utf-8 -*-
"""根容器默认页面"""

from maitux.reviewerassignment.browser.review_queue import ReviewerQueueView


class ReviewerAssignmentDashboard(ReviewerQueueView):
    """默认首页直接复用审核队列"""
