"""Tests for the extraction validation logic."""

import pytest

from src.extractor import is_extraction_valid
from src.models import MetricValue


class TestIsExtractionValid:
    def test_all_values_present(self):
        metrics = [
            MetricValue(name="likes", value=100),
            MetricValue(name="views", value=5000),
        ]
        assert is_extraction_valid(metrics) is True

    def test_some_values_none(self):
        metrics = [
            MetricValue(name="likes", value=100),
            MetricValue(name="views", value=None),
        ]
        assert is_extraction_valid(metrics) is True

    def test_all_values_none(self):
        metrics = [
            MetricValue(name="likes", value=None),
            MetricValue(name="views", value=None),
        ]
        assert is_extraction_valid(metrics) is False

    def test_empty_list(self):
        assert is_extraction_valid([]) is False

    def test_single_valid(self):
        metrics = [MetricValue(name="likes", value=0)]
        assert is_extraction_valid(metrics) is True

    def test_zero_is_valid(self):
        metrics = [MetricValue(name="likes", value=0)]
        assert is_extraction_valid(metrics) is True
