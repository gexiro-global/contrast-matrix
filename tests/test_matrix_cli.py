import json

import pytest

from contrast_matrix.cli import main, render_sarif
from contrast_matrix.matrix import MatrixError, evaluate_matrix, load_matrix, resolve_color


def matrix():
    return {"thresholds": {"normal": 4.5, "large": 3}, "backgrounds": {"bright": "#fff", "dim": "#777", "overlay": "rgba(0,0,0,.5) over #fff", "mixed": "mix(#000, #fff, 0.5)"}, "tokens": [{"name": "ink", "color": "#000", "over": ["bright", "dim"], "level": "normal"}, {"name": "ghost", "color": "rgba(255,255,255,0)", "over": ["bright"], "level": "large"}]}


def test_worst_case_and_determinism():
    result = evaluate_matrix(matrix())
    assert [item["name"] for item in result["results"]] == ["ghost", "ink"]
    ink = result["results"][1]
    assert ink["worst_background"] == "dim"
    assert ink["worst_ratio"] == pytest.approx(4.6895, rel=1e-4)
    assert ink["passed"] is True
    assert result["failure_count"] == 1
    assert result["passed"] is False
    assert [x["background"] for x in ink["comparisons"]] == ["bright", "dim"]


def test_expression_resolution():
    assert resolve_color("rgba(0,0,0,.5) over #fff") == pytest.approx((127.5, 127.5, 127.5, 1))
    assert resolve_color("mix(#000, #fff, .25)") == pytest.approx((63.75, 63.75, 63.75, 1))


def test_named_nested_chained_and_transparent_expressions():
    doc = {
        "backgrounds": {
            "base": "#fff",
            "veil": "rgba(0,0,0,.5)   OVER\tbase",
            "nested": "rgba(255,0,0,.5) over veil over #000",
            "mixed": "mix(veil, mix(#000, #fff, .5), .5)",
        },
        "tokens": [{"name": "clear", "color": "rgba(1,2,3,0)", "over": ["veil"]}],
    }
    result = evaluate_matrix(doc)
    assert result["results"][0]["worst_ratio"] == 1
    assert resolve_color("rgba(1,2,3,0) over rgba(4,5,6,0)") == (0, 0, 0, 0)
    assert resolve_color("rgba(1,2,3,1) over #fff") == (1, 2, 3, 1)


@pytest.mark.parametrize("backgrounds, message", [
    ({"a": "missing"}, "unknown background"),
    ({"a": "a"}, "cyclic"),
    ({"a": "b", "b": "a"}, "cyclic"),
])
def test_unknown_and_cyclic_background_expressions(backgrounds, message):
    doc = {"backgrounds": backgrounds, "tokens": [{"name": "x", "color": "#000", "over": ["a"]}]}
    with pytest.raises(MatrixError, match=message):
        evaluate_matrix(doc)


def test_level_and_fail_under():
    doc = {"backgrounds": {"white": "#fff"}, "tokens": [{"name": "gray", "color": "#595959", "over": ["white"], "level": "normal"}]}
    assert evaluate_matrix(doc, "aa")["passed"] is True
    assert evaluate_matrix(doc, "aaa")["passed"] is True
    assert evaluate_matrix(doc, fail_under=8)["passed"] is False


def test_pass_decision_uses_unrounded_ratio():
    doc = {"backgrounds": {"white": "#fff"}, "tokens": [{"name": "edge", "color": "rgb(118.50001,118.50001,118.50001)", "over": ["white"]}]}
    raw = resolve_color(doc["tokens"][0]["color"])
    from contrast_matrix import contrast_ratio
    threshold = contrast_ratio(raw[:3], (255, 255, 255)) + 0.0000004
    result = evaluate_matrix(doc, fail_under=threshold)
    assert result["results"][0]["worst_ratio"] == round(threshold - 0.0000004, 6)
    assert result["passed"] is False


def test_ties_and_all_pairs_are_deterministic():
    doc = {"backgrounds": {"z": "#fff", "a": "#fff", "m": "#000"}, "tokens": [{"name": "x", "color": "#777", "over": ["z", "m", "a", "z"]}]}
    item = evaluate_matrix(doc)["results"][0]
    assert [pair["background"] for pair in item["comparisons"]] == ["a", "m", "z"]
    assert item["worst_background"] == "a"


@pytest.mark.parametrize("change", [
    {"backgrounds": {}}, {"tokens": []}, {"thresholds": []},
    {"tokens": [{"name": "x", "color": "#000", "over": ["missing"]}]},
    {"tokens": [{"name": "x", "color": "nope", "over": ["bright"]}]},
])
def test_bad_documents(change):
    doc = matrix()
    doc.update(change)
    with pytest.raises(MatrixError):
        evaluate_matrix(doc)


def write_json(tmp_path, doc):
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_cli_exit_codes_and_formats(tmp_path, capsys):
    path = write_json(tmp_path, matrix())
    assert main(["check", str(path), "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["failure_count"] == 1
    assert main(["check", str(path), "--format", "table", "--fail-under", "1"]) == 0
    assert "0 failure(s)" in capsys.readouterr().out
    assert main(["check", str(path), "--format", "sarif"]) == 1
    sarif = json.loads(capsys.readouterr().out)
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"][0]["results"]) == 1


def test_cli_parse_error_is_two(tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    assert main(["check", str(path)]) == 2
    assert "error" in capsys.readouterr().err
    assert main(["check", str(path), "--fail-under", "0"]) == 2
    assert main(["check", str(path), "--fail-under", "nan"]) == 2


def test_malformed_documents_return_two_not_traceback(tmp_path, capsys):
    cases = [
        {"backgrounds": {"white": "#fff"}, "tokens": [{"name": "x", "color": "#000", "over": [["white"]]}]},
        {"backgrounds": {"white": "#fff"}, "thresholds": {"normal": float("nan")}, "tokens": [{"name": "x", "color": "#000", "over": ["white"]}]},
        {"backgrounds": {"white": "mix(#000, #fff, 1.1)"}, "tokens": [{"name": "x", "color": "#000", "over": ["white"]}]},
    ]
    for doc in cases:
        assert main(["check", str(write_json(tmp_path, doc))]) == 2
        assert "error" in capsys.readouterr().err


def test_load_json_and_extension_error(tmp_path):
    path = write_json(tmp_path, matrix())
    assert load_matrix(path)["tokens"][0]["name"] == "ink"
    other = tmp_path / "matrix.txt"
    other.write_text("{}", encoding="utf-8")
    with pytest.raises(MatrixError):
        load_matrix(other)


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"backgrounds": {}, "backgrounds": {}}', encoding="utf-8")
    with pytest.raises(MatrixError, match="duplicate JSON key"):
        load_matrix(path)


def test_invalid_utf8_is_a_clean_input_error(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff")
    assert main(["check", str(path)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_invalid_yaml_is_wrapped(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "bad.yaml"
    path.write_text("backgrounds: [", encoding="utf-8")
    with pytest.raises(MatrixError, match="cannot parse"):
        load_matrix(path)


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "duplicate.yaml"
    path.write_text("backgrounds: {}\nbackgrounds: {}\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="duplicate YAML key"):
        load_matrix(path)


def test_yaml_when_available(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "matrix.yaml"
    path.write_text("backgrounds:\n  white: '#fff'\ntokens:\n  - name: ink\n    color: '#000'\n    over: [white]\n", encoding="utf-8")
    assert load_matrix(path)["backgrounds"]["white"] == "#fff"
