"""
Unit tests for evaluation/statistics.py.

wilson_score_interval() is checked against known textbook values.
paired_significance_test() is checked against scipy's own wilcoxon()
output directly, plus edge cases (identical scores, unequal lengths).
No API calls, no mocking needed — this is pure numerical logic.
"""

import pytest
from scipy import stats as scipy_stats

from evaluation.statistics import paired_significance_test, wilson_score_interval


class TestWilsonScoreInterval:

    def test_point_estimate_matches_simple_ratio(self):
        result = wilson_score_interval(successes=23, n=25)
        assert result["point_estimate"] == pytest.approx(23 / 25)

    def test_interval_bounds_are_within_zero_and_one(self):
        result = wilson_score_interval(successes=23, n=25)
        assert 0.0 <= result["lower"] <= result["point_estimate"] <= result["upper"] <= 1.0

    def test_matches_hand_computed_wilson_formula(self):
        """
        Cross-check against the closed-form Wilson formula computed
        independently (not by calling the function under test), for
        n=25, successes=23, z=1.959963985 (95% CI):
          p_hat = 0.92
          centre = (0.92 + z^2/50) / (1 + z^2/25) = 0.9077...
          margin = z * sqrt(p_hat*(1-p_hat)/25 + z^2/2500) / (1 + z^2/25) = 0.1084...
        giving bounds of approximately (0.750, 0.978).
        """
        result = wilson_score_interval(successes=23, n=25)
        assert result["lower"] == pytest.approx(0.750, abs=0.01)
        assert result["upper"] == pytest.approx(0.978, abs=0.01)

    def test_small_n_produces_wide_interval(self):
        """A small sample (n=8) should produce a visibly wide interval, not a falsely precise one."""
        result = wilson_score_interval(successes=7, n=8)
        width = result["upper"] - result["lower"]
        assert width > 0.25  # wide — this is the point of using Wilson at small n

    def test_zero_trials_returns_zeros_not_error(self):
        result = wilson_score_interval(successes=0, n=0)
        assert result == {"point_estimate": 0.0, "lower": 0.0, "upper": 0.0, "n": 0}

    def test_perfect_score_interval_still_bounded_below_one(self):
        """100% accuracy shouldn't report an interval of exactly [1.0, 1.0] — some uncertainty remains at finite n."""
        result = wilson_score_interval(successes=10, n=10)
        assert result["point_estimate"] == 1.0
        assert result["lower"] < 1.0

    def test_zero_successes_interval_still_bounded_above_zero_when_n_large(self):
        result = wilson_score_interval(successes=0, n=25)
        assert result["point_estimate"] == 0.0
        assert result["upper"] > 0.0


class TestPairedSignificanceTest:

    def test_matches_scipy_wilcoxon_directly(self):
        a = [12, 11, 12, 10, 12, 9, 12, 11, 12, 10]
        b = [6, 5, 8, 6, 5, 7, 6, 5, 8, 6]
        result = paired_significance_test(a, b, "RAG+", "RAG-only")
        expected_stat, expected_p = scipy_stats.wilcoxon(a, b)
        assert result["statistic"] == pytest.approx(float(expected_stat))
        assert result["p_value"] == pytest.approx(float(expected_p))

    def test_significant_flag_matches_p_value_threshold(self):
        a = [12, 11, 12, 10, 12, 9, 12, 11, 12, 10]
        b = [6, 5, 8, 6, 5, 7, 6, 5, 8, 6]
        result = paired_significance_test(a, b)
        assert result["significant"] == (result["p_value"] < 0.05)

    def test_labels_are_passed_through(self):
        result = paired_significance_test([1, 2, 3], [1, 2, 4], "X", "Y")
        assert result["label_a"] == "X"
        assert result["label_b"] == "Y"

    def test_identical_scores_return_non_significant_without_raising(self):
        """scipy.stats.wilcoxon raises on all-zero differences — this must degrade gracefully instead."""
        result = paired_significance_test([8, 8, 8], [8, 8, 8])
        assert result["p_value"] == 1.0
        assert result["significant"] is False
        assert result["n_pairs"] == 3

    def test_unequal_length_raises_value_error(self):
        with pytest.raises(ValueError):
            paired_significance_test([1, 2, 3], [1, 2])

    def test_n_pairs_matches_input_length(self):
        result = paired_significance_test([1, 2, 3, 4], [2, 3, 4, 5])
        assert result["n_pairs"] == 4
