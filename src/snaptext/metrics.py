"""Accuracy metrics for comparing OCR output against ground truth."""

from __future__ import annotations

from collections.abc import Hashable, Sequence


def normalise(text: str) -> str:
    """Collapse every run of whitespace, including line breaks, to one space."""
    return " ".join(text.split())


def levenshtein(a: Sequence[Hashable], b: Sequence[Hashable]) -> int:
    """Return the minimum number of single-item edits that turn ``a`` into ``b``."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (item_a != item_b),
                )
            )
        previous = current
    return previous[-1]


def _accuracy(expected: Sequence[Hashable], actual: Sequence[Hashable]) -> float:
    if not expected:
        return 0.0 if actual else 1.0
    return max(0.0, 1.0 - levenshtein(expected, actual) / len(expected))


def character_accuracy(expected: str, actual: str) -> float:
    """Return 1 minus the character error rate, clamped to the range 0 to 1."""
    return _accuracy(normalise(expected), normalise(actual))


def word_accuracy(expected: str, actual: str) -> float:
    """Return 1 minus the word error rate, clamped to the range 0 to 1."""
    return _accuracy(normalise(expected).split(), normalise(actual).split())
