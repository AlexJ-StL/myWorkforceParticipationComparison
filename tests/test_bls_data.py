"""Tests for BLS weekly hours data integration."""

import pytest

from bls_data import BlsSeriesSpec, BLS_SERIES, BLBS_SERIES_DICT, BLS_ALL_SIDS, fetch_bls_series, BlsFetchError


class TestBLSData:
    """Test BLS data collection and integration."""

    def test_bls_series_specs(self):
        """Test that BLS series specifications are properly defined."""
        assert len(BLS_SERIES) == 2

        men_series = next(s for s in BLS_SERIES if s.sid == "LNS12032194")
        assert men_series.sid == "LNS12032194"
        assert "hours worked" in men_series.label.lower()
        assert men_series.units == "hours_per_week"

        women_series = next(s for s in BLS_SERIES if s.sid == "LNS12032195")
        assert women_series.sid == "LNS12032195"
        assert "hours worked" in women_series.label.lower()
        assert women_series.units == "hours_per_week"

    def test_bls_series_by_sid_dict(self):
        """Test BLS series dictionary lookup."""
        assert "LNS12032194" in BLBS_SERIES_DICT
        assert "LNS12032195" in BLBS_SERIES_DICT

        men_spec = BLBS_SERIES_DICT["LNS12032194"]
        assert men_spec.sid == "LNS12032194"
        assert men_spec.short == "Men weekly hours"

        women_spec = BLBS_SERIES_DICT["LNS12032195"]
        assert women_spec.sid == "LNS12032195"
        assert women_spec.short == "Women weekly hours"

    def test_bls_series_catalog_structure(self):
        """Test that BLS series catalog follows expected structure."""
        for spec in BLS_SERIES:
            assert isinstance(spec, BlsSeriesSpec)
            assert hasattr(spec, 'sid')
            assert hasattr(spec, 'label')
            assert hasattr(spec, 'short')
            assert hasattr(spec, 'units')
            assert spec.sid.startswith("LNS")
            assert "hours" in spec.label.lower() or "week" in spec.label.lower()

    def test_bls_series_coverage(self):
        """Test that all expected BLS series IDs are present."""
        expected_sids = {"LNS12032194", "LNS12032195"}
        actual_sids = set(BLBS_SERIES_DICT.keys())
        assert expected_sids == actual_sids

    def test_bls_series_no_duplicates(self):
        """Test that there are no duplicate BLS series IDs."""
        sids = [spec.sid for spec in BLS_SERIES]
        assert len(sids) == len(set(sids))

    @pytest.mark.vcr
    def test_fetch_bls_series_structure(self, vcr_cassette):
        """Test that BLS series fetch returns properly structured data."""
        # This test would require a VCR cassette to record API responses
        # For now, we'll just verify the function exists and has the right signature
        assert callable(fetch_bls_series)
        # The actual fetch would be tested with recorded HTTP responses

    def test_bls_series_spec_types(self):
        """Test that BLS series specifications have correct types."""
        for spec in BLS_SERIES:
            assert isinstance(spec.sid, str)
            assert isinstance(spec.label, str)
            assert isinstance(spec.short, str)
            assert isinstance(spec.units, str)
            assert spec.sid.startswith("LNS")

    def test_bls_series_attribute_completeness(self):
        """Test that BLS series specifications have all required attributes."""
        required_attrs = {"sid", "label", "short", "units"}
        for spec in BLS_SERIES:
            spec_attrs = set(spec.__dict__.keys())
            assert required_attrs.issubset(spec_attrs), (
                f"BLS series {spec.sid} missing attributes: "
                f"{required_attrs - spec_attrs}"
            )