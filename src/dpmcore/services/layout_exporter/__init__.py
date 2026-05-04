"""Annotated table layout exporter.

Generates Excel workbooks with formatted DPM table layouts including
hierarchical headers, data-point cells, dimensional annotations,
and categorisation tooltips.
"""

from dpmcore.services.layout_exporter.service import LayoutExporterService

__all__ = ["LayoutExporterService"]
