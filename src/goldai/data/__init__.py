"""Canonical historical market-data ingestion, auditing, and persistence."""

from goldai.data.aggregation import CanonicalCandleAggregator, MultiTimeframeAggregator
from goldai.data.audit import DataAuditReport, SpreadStatistics, audit_histdata
from goldai.data.histdata import HistDataAdapter, TickRecord
from goldai.data.manifest import DataManifest
from goldai.data.prepare import PreparationResult, prepare_histdata
from goldai.data.quality import DataQualityStatus

__all__ = [
    "CanonicalCandleAggregator",
    "DataAuditReport",
    "DataManifest",
    "DataQualityStatus",
    "HistDataAdapter",
    "MultiTimeframeAggregator",
    "PreparationResult",
    "SpreadStatistics",
    "TickRecord",
    "audit_histdata",
    "prepare_histdata",
]
