"""Plugin SDK for looker-extractor.

The Plugin Protocol/ABC and minimal helpers live here so plugin authors can
depend on ``looker-extractor-sdk`` alone (light dep footprint) without
pulling the ``looker-extractor`` core CLI + writers + httpx + pyarrow.

This separation follows the dbt-adapters pattern — see ARCHITECTURE.md
"Agent 1: Plugin patterns survey" for the rationale.

Phase 1 ships this package as a stub. The Plugin base + lineage helpers
extract from ``looker-extractor`` core in Phase 2.
"""

__version__ = "0.1.0a0"
