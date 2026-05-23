"""Conformance: lookml_fields plugin meets the SDK contract.

Inherits the 9 generic conformance tests from BasePluginContract
(looker-extractor-tests-plugin). Adds 2 lookml_fields-specific pins.

Extract-behavior tests pytest.skip because lookml_fields uses higher-level
LookerClient methods (all_lookml_models, lookml_model_explore) rather than
a single .get() — mocking is awkward. End-to-end extraction is exercised
in integration tests against a live Looker instance.
"""

from __future__ import annotations

from looker_extractor_tests_plugin import BasePluginContract

from looker_extractor.plugins.lookml_fields.plugin import LookmlFieldsPlugin


class TestLookmlFieldsConformance(BasePluginContract):
    """Full harness; fake_client NOT overridden → 2 extract tests skip cleanly."""

    plugin_class = LookmlFieldsPlugin

    # ------------------------------------------------------------------
    # lookml_fields-specific (in addition to inherited harness)
    # ------------------------------------------------------------------

    def test_lookml_fields_name_pinned(self) -> None:
        """name is the entry-point key + the CLI --plugin flag; never change accidentally."""
        assert self.plugin_class.name == "lookml_fields"

    def test_lookml_fields_swagger_seeds_count(self) -> None:
        """Pin seed list to catch accidental drift between regenerations."""
        seeds = self.plugin_class.swagger_seeds
        assert len(seeds) == 12
        assert "LookmlModelExplore" in seeds
        assert "LookmlModelExploreField" in seeds
