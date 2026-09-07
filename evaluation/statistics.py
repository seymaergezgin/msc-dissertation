"""
Statistical analysis of Phase 6/7 evaluation results.

Why this exists: the Phase 6 report presented point estimates — "92%
routing accuracy," mean ablation scores — with no measure of uncertainty.
An external dissertation review correctly identified this as a gap: with
n=25-38 for routing and n=9-15 per ablation condition, a bare percentage or
mean overstates precision an examiner will expect to see acknowledged.

This module adds exactly two things, deliberately not a general statistics
library:
  - wilson_score_interval(): a confidence interval for a binomial proportion
    (routing accuracy), more accurate than the normal approximation at the
    small-to-moderate sample sizes involved here
  - paired_significance_test(): a Wilcoxon signed-rank test comparing two
    paired sets of judge scores (e.g. RAG+ vs RAG-only on the same queries)

Usage:
    from evaluation.statistics import wilson_score_interval, paired_significance_test

    ci = wilson_score_interval(successes=23, n=25)
    print(f"{ci['point_estimate']:.1%} (95% CI: {ci['lower']:.1%}-{ci['upper']:.1%})")

    result = paired_significance_test(rag_plus_scores, rag_only_scores, "RAG+", "RAG-only")
    print(result["p_value"], result["significant"])
"""

import logging

from scipy import stats

logger = logging.getLogger(__name__)


def wilson_score_interval(successes: int, n: int, confidence: float = 0.95) -> dict:
    """
    Compute the Wilson score confidence interval for a binomial proportion.

    Chosen over the normal-approximation ("Wald") interval because the
    Wilson interval stays well-behaved at small n and at proportions near
    0 or 1 — both apply here (routing-accuracy samples as small as n=8 for
    a single agent, and proportions as high as 92%). The normal
    approximation can produce nonsensical intervals (bounds outside [0,1])
    in exactly these conditions; Wilson does not.

    Args:
        successes: Number of correct outcomes (e.g. correctly routed queries).
        n: Total number of trials.
        confidence: Confidence level (default 0.95 for a 95% CI).

    Returns:
        Dict with "point_estimate", "lower", "upper" (proportions in [0,1]),
        and "n". Returns all zeros if n=0 rather than raising, since a
        zero-sample subgroup is possible when scoring is broken down
        per-agent.
    """
    if n == 0:
        return {"point_estimate": 0.0, "lower": 0.0, "upper": 0.0, "n": 0}

    p_hat = successes / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    margin = z * ((p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) ** 0.5)

    return {
        "point_estimate": p_hat,
        "lower": max(0.0, (centre - margin) / denom),
        "upper": min(1.0, (centre + margin) / denom),
        "n": n,
    }


def paired_significance_test(
    scores_a: list[float],
    scores_b: list[float],
    label_a: str = "A",
    label_b: str = "B",
) -> dict:
    """
    Wilcoxon signed-rank test comparing two paired sets of scores.

    Used to test, e.g., whether RAG+ judge totals are significantly higher
    than RAG-only judge totals on the same queries. A non-parametric,
    paired test was chosen over a paired t-test because judge scores (0-12)
    are ordinal/bounded rather than continuous, and the ablation sample
    sizes here (n=9-15 per condition) are too small to safely assume
    normality — the Wilcoxon test makes no such assumption.

    Args:
        scores_a: Scores under condition A, one per query.
        scores_b: Scores under condition B, on the SAME queries in the
                  same order (paired data — this is not an independent-
                  samples test).
        label_a, label_b: Human-readable labels included in the result,
                           for report generation.

    Returns:
        Dict with "statistic", "p_value", "significant" (p < 0.05),
        "n_pairs", "label_a", "label_b".

    Raises:
        ValueError: If scores_a and scores_b are not the same length.
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("scores_a and scores_b must be the same length (paired data)")

    differences = [a - b for a, b in zip(scores_a, scores_b)]
    if all(d == 0 for d in differences):
        # scipy.stats.wilcoxon raises on all-zero differences (nothing to
        # rank) — this is a real "no difference detected" result, not an
        # error, so it should be reported as such rather than propagating
        # an exception up to the evaluation report generator.
        logger.info(
            "paired_significance_test: %s vs %s — all %d pairs identical, no difference to test.",
            label_a, label_b, len(scores_a),
        )
        return {
            "statistic": 0.0, "p_value": 1.0, "significant": False,
            "n_pairs": len(scores_a), "label_a": label_a, "label_b": label_b,
        }

    statistic, p_value = stats.wilcoxon(scores_a, scores_b)
    return {
        "statistic": float(statistic),
        "p_value": float(p_value),
        "significant": p_value < 0.05,
        "n_pairs": len(scores_a),
        "label_a": label_a,
        "label_b": label_b,
    }
