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


def test_level_and_fail_under():
    doc = {"backgrounds": {"white": "#fff"}, "tokens": [{"name": "gray", "color": "#595959", "over": ["white"], "level": "normal"}]}
    assert evaluate_matrix(doc, "aa")["passed"] is True
    assert evaluate_matrix(doc, "aaa")["passed"] is True
    assert evaluate_matrix(doc, fail_under=8)["passed"] is False


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


def test_load_json_and_extension_error(tmp_path):
    path = write_json(tmp_path, matrix())
    assert load_matrix(path)["tokens"][0]["name"] == "ink"
    other = tmp_path / "matrix.txt"
    other.write_text("{}", encoding="utf-8")
    with pytest.raises(MatrixError):
        load_matrix(other)


def test_yaml_when_available(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "matrix.yaml"
    path.write_text("backgrounds:\n  white: '#fff'\ntokens:\n  - name: ink\n    color: '#000'\n    over: [white]\n", encoding="utf-8")
    assert load_matrix(path)["backgrounds"]["white"] == "#fff"

