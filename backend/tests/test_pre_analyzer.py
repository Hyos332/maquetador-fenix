from app.services.pre_analyzer import _smart_trim_abstract
from app.utils.strings import word_count


def test_smart_trim_removes_minimal_low_impact_words() -> None:
    base = " ".join(f"palabra{i}" for i in range(248))
    text = f"{base} además también especialmente conclusión final."

    trimmed = _smart_trim_abstract(text, max_words=250)

    assert word_count(text) == 253
    assert word_count(trimmed) == 250
    assert "conclusión final" in trimmed
    assert "palabra247" in trimmed
    assert "además" not in trimmed


def test_smart_trim_removes_repeated_small_words_before_truncating() -> None:
    text = " ".join(["El estudio que que que"] + [f"dato{i}" for i in range(247)])

    trimmed = _smart_trim_abstract(text, max_words=250)

    assert word_count(trimmed) == 250
    assert "que que" not in trimmed
    assert "dato246" in trimmed
