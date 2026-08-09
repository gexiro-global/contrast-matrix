"""Declarative contrast matrix loading and evaluation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from .kernel import ColorError, RGBA, contrast_ratio, mix, over, parse_color

DEFAULT_THRESHOLDS = {"normal": 4.5, "large": 3.0, "aaa_normal": 7.0, "aaa_large": 4.5}


class MatrixError(ValueError):
    """Raised for malformed matrix documents."""


def load_matrix(path: Path) -> Mapping[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MatrixError("cannot read {}: {}".format(path, exc)) from exc
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(raw)
        elif path.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as exc:
                raise MatrixError("YAML input requires: pip install 'contrast-matrix[yaml]'") from exc
            data = yaml.safe_load(raw)
        else:
            raise MatrixError("input extension must be .json, .yaml, or .yml")
    except (json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, MatrixError):
            raise
        raise MatrixError("cannot parse {}: {}".format(path, exc)) from exc
    if not isinstance(data, dict):
        raise MatrixError("matrix root must be an object")
    return data


def resolve_color(expression: str) -> RGBA:
    """Resolve a CSS color, `A over B`, or `mix(A, B, t)` expression."""
    if not isinstance(expression, str):
        raise MatrixError("color expression must be a string")
    parts = re.split(r"\s+over\s+", expression.strip(), maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        foreground, background = (resolve_color(part) for part in parts)
        backdrop = over(background, (255.0, 255.0, 255.0))
        return over(foreground, backdrop) + (1.0,)
    match = re.fullmatch(r"(?is)mix\((.+),\s*(.+),\s*([0-9]*\.?[0-9]+)\)", expression.strip())
    if match:
        return mix(resolve_color(match.group(1).strip()), resolve_color(match.group(2).strip()), float(match.group(3)))
    try:
        return parse_color(expression)
    except ColorError as exc:
        raise MatrixError(str(exc)) from exc


def evaluate_matrix(document: Mapping[str, Any], level: str = "aa", fail_under: float = None) -> Dict[str, Any]:
    """Evaluate all token/background pairs and reduce each token to its minimum."""
    backgrounds = document.get("backgrounds")
    tokens = document.get("tokens")
    if not isinstance(backgrounds, dict) or not backgrounds:
        raise MatrixError("backgrounds must be a non-empty object")
    if not isinstance(tokens, list) or not tokens:
        raise MatrixError("tokens must be a non-empty array")
    thresholds = dict(DEFAULT_THRESHOLDS)
    custom = document.get("thresholds", {})
    if not isinstance(custom, dict):
        raise MatrixError("thresholds must be an object")
    for name, value in custom.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise MatrixError("threshold {!r} must be a positive number".format(name))
        thresholds[str(name)] = float(value)
    resolved = {str(name): resolve_color(value) for name, value in backgrounds.items()}
    results: List[Dict[str, Any]] = []
    seen = set()
    for token in tokens:
        if not isinstance(token, dict):
            raise MatrixError("each token must be an object")
        name, color, over_names = token.get("name"), token.get("color"), token.get("over")
        if not isinstance(name, str) or not name or name in seen:
            raise MatrixError("token names must be unique non-empty strings")
        seen.add(name)
        if not isinstance(over_names, list) or not over_names:
            raise MatrixError("token {!r} must list at least one background".format(name))
        base_level = token.get("level", "normal")
        threshold_name = "aaa_" + base_level if level == "aaa" and not str(base_level).startswith("aaa_") else str(base_level)
        if threshold_name not in thresholds:
            raise MatrixError("token {!r} uses unknown threshold {!r}".format(name, threshold_name))
        required = float(fail_under) if fail_under is not None else thresholds[threshold_name]
        foreground = resolve_color(color)
        pairs = []
        for background_name in sorted(set(over_names)):
            if background_name not in resolved:
                raise MatrixError("token {!r} references unknown background {!r}".format(name, background_name))
            background_rgba = resolved[background_name]
            background_rgb = over(background_rgba, (255.0, 255.0, 255.0))
            effective = over(foreground, background_rgb)
            ratio = contrast_ratio(effective, background_rgb)
            pairs.append({"background": background_name, "ratio": round(ratio, 6)})
        worst = min(pairs, key=lambda item: (item["ratio"], item["background"]))
        results.append({"name": name, "level": threshold_name, "threshold": required, "passed": worst["ratio"] + 1e-12 >= required, "worst_background": worst["background"], "worst_ratio": worst["ratio"], "comparisons": pairs})
    results.sort(key=lambda item: item["name"])
    failures = sum(not item["passed"] for item in results)
    return {"wcag_version": "WCAG 2.x", "level": level, "token_count": len(results), "failure_count": failures, "passed": failures == 0, "results": results}

