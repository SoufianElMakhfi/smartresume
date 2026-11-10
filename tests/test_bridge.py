import pytest

from smartresume import bridge, generate


def test_chat_prompt_contains_rules_and_task():
    p = bridge.chat_prompt("REGELN: nur JSON", "AUFTRAG: Bewerbung")
    assert p.index("REGELN") < p.index("AUFTRAG")
    assert "```json" in p


@pytest.mark.parametrize("answer", [
    '{"summary": "x"}',
    'Gerne! Hier ist das Ergebnis:\n```json\n{"summary": "x",}\n```\nViel Erfolg!',
    '```\n{"summary": "x"}\n```',
])
def test_parse_answer_tolerates_chat_formatting(answer):
    assert bridge.parse_answer(answer) == {"summary": "x"}


def test_parse_answer_errors_are_understandable():
    with pytest.raises(ValueError, match="keine Antwort"):
        bridge.parse_answer("   ")
    with pytest.raises(ValueError, match="kein vollständiges JSON"):
        bridge.parse_answer("Leider kann ich das nicht.")
    with pytest.raises(ValueError, match="unvollständig: cover_letter"):
        bridge.parse_answer('{"summary": "x", "experience": []}', generate.validate_ai)
    assert "erneut" in bridge.correction_prompt("x")


def test_repair_helpers():
    s = {"cover_letter": {"salutation": "Hallo,", "p1": "alt", "p2": "b", "p3": "c", "p4": "d"}}
    system, user = generate.repair_prompts(s, ["Platzhalter gefunden"], {"personal": {"name": "Max"}} | _min_profile())
    assert "Platzhalter gefunden" in user and "alt" in user
    assert generate.validate_repair({"foo": 1})
    generate.apply_repair(s, {"p1": "neu", "evil": "x", "p2": "  "})
    assert s["cover_letter"]["p1"] == "neu" and s["cover_letter"]["p2"] == "b" and "evil" not in s["cover_letter"]


def _min_profile():
    from smartresume.profile import empty_profile
    return empty_profile()
