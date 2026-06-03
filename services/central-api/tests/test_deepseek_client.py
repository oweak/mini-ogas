from app.core.deepseek_client import _bounded_float, _parse_json_content


def test_parse_json_content_strips_code_fence() -> None:
    parsed = _parse_json_content(
        """```json
        {"root_cause": "cpu pressure", "confidence": 0.7}
        ```"""
    )

    assert parsed["root_cause"] == "cpu pressure"
    assert parsed["confidence"] == 0.7


def test_parse_json_content_falls_back_to_regex() -> None:
    parsed = _parse_json_content('analysis text {"recommended_action": "restart"} tail')

    assert parsed["recommended_action"] == "restart"


def test_bounded_float_clamps_0_to_1() -> None:
    assert _bounded_float(-2, 0.5) == 0.0
    assert _bounded_float(2, 0.5) == 1.0
    assert _bounded_float("bad", 0.5) == 0.5
