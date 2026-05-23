"""Reference plugin: explore-field passthru extractor.

This is the v0.3.0a0 reference shape that all other plugins follow:
swagger-typed validate -> model_dump -> stamp lineage envelope. The Plugin
class wrapper + entry-point wiring land in a follow-up iteration; for now
the extractor is exposed via plain async generators.
"""

from .extract import extract_explore_fields, flatten_explore_fields

__all__ = ["extract_explore_fields", "flatten_explore_fields"]
