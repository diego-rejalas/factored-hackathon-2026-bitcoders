"""The statistics the evaluation reports, small enough to read and test.

Everything here is computed from counts, so a result can be recomputed from the committed per-case files.
"""

import math
from collections import Counter


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """The Wilson score interval for a proportion. None when there is nothing to measure."""
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(successes: int, total: int) -> dict:
    """A proportion with its denominator and interval, or "not defined" when the denominator is zero."""
    if total == 0:
        return {"n": 0, "k": 0, "value": None, "ci95": None}
    interval = wilson(successes, total)
    return {"n": total, "k": successes, "value": round(successes / total, 4), "ci95": [round(interval[0], 4), round(interval[1], 4)]}


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact p-value for paired outcomes: only_a cases only system A got right, only_b only B."""
    discordant = only_a + only_b
    if discordant == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(discordant, i) for i in range(0, k + 1)) / 2**discordant
    return min(1.0, 2 * tail)


def percentile(values: list[float], q: float) -> float | None:
    """Linear interpolation, the same definition the agent's own metrics use."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def confusion(pairs: list[tuple[str, str]], labels: list[str]) -> dict:
    """{expected: {predicted: count}} for the given labels; anything else is counted as "other"."""
    table = {expected: Counter() for expected in labels}
    for expected, predicted in pairs:
        table[expected][predicted if predicted in labels else "other"] += 1
    return {expected: dict(counts) for expected, counts in table.items()}


def macro_f1(pairs: list[tuple[str, str]], labels: list[str]) -> float | None:
    scores = []
    for label in labels:
        tp = sum(1 for e, p in pairs if e == label and p == label)
        fp = sum(1 for e, p in pairs if e != label and p == label)
        fn = sum(1 for e, p in pairs if e == label and p != label)
        if tp + fp + fn == 0:
            continue
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))
    return round(sum(scores) / len(scores), 4) if scores else None
