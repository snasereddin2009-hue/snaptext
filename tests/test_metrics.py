import pytest

from snaptext.metrics import character_accuracy, levenshtein, normalise, word_accuracy


@pytest.mark.parametrize(
    ("a", "b", "distance"),
    [
        ("", "", 0),
        ("abc", "abc", 0),
        ("", "abc", 3),
        ("abc", "", 3),
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
        ("abc", "abd", 1),
    ],
)
def test_levenshtein(a: str, b: str, distance: int) -> None:
    assert levenshtein(a, b) == distance


def test_levenshtein_is_symmetric() -> None:
    assert levenshtein("sunday", "saturday") == levenshtein("saturday", "sunday") == 3


def test_levenshtein_accepts_word_sequences() -> None:
    assert levenshtein(["the", "quick", "fox"], ["the", "slow", "fox"]) == 1


def test_normalise_collapses_whitespace() -> None:
    assert normalise("  hello \n\n world\t!  ") == "hello world !"


def test_character_accuracy_of_exact_match_is_one() -> None:
    assert character_accuracy("Hello, world", "Hello, world") == 1.0


def test_character_accuracy_ignores_whitespace_layout() -> None:
    assert character_accuracy("line one\nline two", "line one  line two\n") == 1.0


def test_character_accuracy_counts_edits() -> None:
    assert character_accuracy("abcdefghij", "abcdefghiX") == pytest.approx(0.9)


def test_character_accuracy_is_case_sensitive() -> None:
    assert character_accuracy("Text", "text") == pytest.approx(0.75)


def test_character_accuracy_is_clamped_at_zero() -> None:
    assert character_accuracy("ab", "completely different output") == 0.0


def test_accuracy_with_no_output_is_zero() -> None:
    assert character_accuracy("some text", "") == 0.0
    assert word_accuracy("some text", "") == 0.0


def test_accuracy_with_empty_ground_truth() -> None:
    assert character_accuracy("", "") == 1.0
    assert character_accuracy("", "noise") == 0.0


def test_word_accuracy_counts_whole_words() -> None:
    assert word_accuracy("the quick brown fox", "the quick brawn fox") == pytest.approx(0.75)


def test_word_accuracy_penalises_missing_words() -> None:
    assert word_accuracy("one two three four", "one two") == pytest.approx(0.5)
