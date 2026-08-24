# -*- coding: utf-8 -*-
from zope.interface import Interface


class IProjects(Interface):
    """Marker interface for Projects container (仿 Batches/BatchFolder)
    """


class IProject(Interface):
    """Marker interface for a single Project (仿 Batch)
    """
