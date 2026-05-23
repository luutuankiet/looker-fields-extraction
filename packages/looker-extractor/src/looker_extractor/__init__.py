"""looker-extractor: plugin-based passthru extractor for the Looker v4.0 API.

Reference plugin: ``lookml_fields`` (the v0.3.0a0 passthru shape — one row per
field, swagger-validated, dumped natural-nested to JSONL/Parquet, lineage
envelope on each row). Additional entity plugins follow the same shape.

Post-pivot vision: meltano-for-looker. Plugin SDK lives in the separate
``looker-extractor-sdk`` package so plugin authors don't pull the core
CLI dependency tree.
"""

__version__ = "0.3.0a0"
