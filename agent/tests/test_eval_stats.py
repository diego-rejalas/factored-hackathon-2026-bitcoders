from eval import stats


def test_wilson_matches_known_values():
    low, high = stats.wilson(8, 10)
    assert round(low, 3) == 0.490 and round(high, 3) == 0.943
    assert stats.wilson(0, 0) is None
    low, high = stats.wilson(0, 20)
    assert low == 0.0 and round(high, 3) == 0.161  # zero failures is not zero risk: the interval says so


def test_a_rate_with_no_denominator_is_not_defined_not_zero():
    assert stats.rate(0, 0) == {"n": 0, "k": 0, "value": None, "ci95": None}
    assert stats.rate(3, 4)["value"] == 0.75


def test_mcnemar_exact():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(5, 5) == 1.0
    assert round(stats.mcnemar_exact(0, 10), 5) == round(2 / 1024, 5)  # all ten discordant pairs favour one system
    assert stats.mcnemar_exact(2, 8) == stats.mcnemar_exact(8, 2)


def test_percentile_interpolates_like_the_agent_metrics():
    assert stats.percentile([], 0.5) is None
    assert stats.percentile([7], 0.95) == 7.0
    assert stats.percentile([1, 2, 3, 4], 0.5) == 2.5
    assert stats.percentile([1, 2, 3, 4], 0.95) == 3.85


def test_confusion_and_macro_f1():
    pairs = [("a", "a"), ("a", "b"), ("b", "b"), ("b", "b"), ("b", "zzz")]
    assert stats.confusion(pairs, ["a", "b"]) == {"a": {"a": 1, "b": 1}, "b": {"b": 2, "other": 1}}
    assert stats.macro_f1([("a", "a"), ("b", "b")], ["a", "b"]) == 1.0
    assert stats.macro_f1([], ["a"]) is None
