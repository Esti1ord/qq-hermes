import math

import pytest

from qq_hermes_bridge import jrrp


FIXED_SEED = "2026060221052544866989"


@pytest.mark.parametrize(
    ("score", "expected_name"),
    [
        (0, "大凶"),
        (4, "大凶"),
        (5, "凶"),
        (19, "凶"),
        (20, "小凶"),
        (39, "小凶"),
        (40, "平"),
        (59, "平"),
        (60, "小吉"),
        (74, "小吉"),
        (75, "中吉"),
        (89, "中吉"),
        (90, "大吉"),
        (99, "大吉"),
        (100, "天选之人"),
    ],
)
def test_level_for_score_uses_builtin_default_boundaries(score, expected_name):
    assert jrrp.level_for_score({}, score)["name"] == expected_name


def test_level_for_score_invalid_custom_results_fall_back_to_builtin_defaults():
    invalid_results = [
        {"levels": "not a list"},
        {"levels": []},
        {"levels": [None]},
        {"levels": [{"name": "broken"}]},
        {"levels": [{"min": 0, "max": 100}]},
        {"levels": [{"name": "broken", "min": "bad", "max": 100}]},
        {"levels": [{"name": "broken", "min": 90, "max": "bad"}]},
        {"levels": [{"name": "broken", "min": 100, "max": 90}]},
    ]

    for results in invalid_results:
        assert jrrp.level_for_score(results, 100)["name"] == "天选之人"
        assert jrrp.level_for_score(results, 3)["name"] == "大凶"


def test_level_for_score_custom_levels_override_when_matching():
    results = {
        "levels": [
            {"name": "自定义低分", "min": 0, "max": 50, "faces": ["low"], "comments": ["low comment"]},
            {"name": "自定义高分", "min": 51, "max": 100, "faces": ["high"], "comments": ["high comment"]},
        ]
    }

    assert jrrp.level_for_score(results, 40)["name"] == "自定义低分"
    assert jrrp.level_for_score(results, 90)["name"] == "自定义高分"


def test_level_for_score_custom_levels_fall_back_when_no_custom_match():
    results = {"levels": [{"name": "自定义小段", "min": 10, "max": 12}]}

    assert jrrp.level_for_score(results, 100)["name"] == "天选之人"
    assert jrrp.level_for_score(results, 0)["name"] == "大凶"


def test_score_for_seed_is_deterministic_integer_in_range():
    score = jrrp.score_for_seed(FIXED_SEED)

    assert isinstance(score, int)
    assert 0 <= score <= 100
    assert score == jrrp.score_for_seed(FIXED_SEED)


def test_score_for_seed_uses_asymmetric_gaussian_mixture_shape():
    def density(score):
        total = 0.0
        for weight, mean, stdev in jrrp.JRRP_SCORE_COMPONENTS:
            total += weight * math.exp(-((score - mean) ** 2) / (2 * stdev**2)) / stdev
        return total

    scores = list(range(101))
    mode = max(scores, key=density)

    assert mode == 75
    assert all(density(score) <= density(score + 1) for score in range(75))
    assert all(density(score) >= density(score + 1) for score in range(75, 100))
    assert density(50) > density(100)
    assert density(0) < density(50) < density(75)
    assert density(75) > density(90) > density(100)


def test_score_for_seed_distribution_keeps_100_rare_without_clamping_pileup():
    scores = [jrrp.score_for_seed(f"shape:{idx}") for idx in range(20_000)]
    counts = {score: scores.count(score) for score in range(101)}
    mode = max(counts, key=counts.get)

    assert 70 <= mode <= 80
    assert counts[100] < counts[95] < counts[90] < counts[80]
    assert counts[100] < len(scores) * 0.002
    assert sum(counts[score] for score in range(0, 40)) > sum(counts[score] for score in range(90, 101))
