"""Declarative contrast matrix loading and evaluation."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from .kernel import ColorError, RGBA, composite, contrast_ratio, mix, over, parse_color

DEFAULT_THRESHOLDS = {"normal": 4.5, "large": 3.0, "aaa_normal": 7.0, "aaa_large": 4.5}


class MatrixError(ValueError):
    """Raised for malformed matrix documents."""


def load_matrix(path: Path) -> Mapping[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise MatrixError("cannot read {}: {}".format(path, exc)) from exc
    try:
        if path.suffix.lower() == ".json":
            def reject_duplicates(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
                result: Dict[str, Any] = {}
                for key, value in pairs:
                    if key in result:
                        raise MatrixError("duplicate JSON key: {!r}".format(key))
                    result[key] = value
                return result
            data = json.loads(raw, object_pairs_hook=reject_duplicates)
        elif path.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as exc:
                raise MatrixError("YAML input requires: pip install 'contrast-matrix[yaml]'") from exc
            class UniqueKeyLoader(yaml.SafeLoader):
                pass

            def construct_unique_mapping(loader: Any, node: Any, deep: bool = False) -> Dict[Any, Any]:
                loader.flatten_mapping(node)
                result: Dict[Any, Any] = {}
                for key_node, value_node in node.value:
                    key = loader.construct_object(key_node, deep=deep)
                    try:
                        duplicate = key in result
                    except TypeError as exc:
                        raise MatrixError("YAML mapping keys must be scalar") from exc
                    if duplicate:
                        raise MatrixError("duplicate YAML key: {!r}".format(key))
                    result[key] = loader.construct_object(value_node, deep=deep)
                return result

            UniqueKeyLoader.add_constructor(
                yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping
            )
            try:
                data = yaml.load(raw, Loader=UniqueKeyLoader)
            except yaml.YAMLError as exc:
                raise MatrixError("cannot parse {}: {}".format(path, exc)) from exc
        else:
            raise MatrixError("input extension must be .json, .yaml, or .yml")
    except (json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, MatrixError):
            raise
        raise MatrixError("cannot parse {}: {}".format(path, exc)) from exc
    if not isinstance(data, dict):
        raise MatrixError("matrix root must be an object")
    return data


def _split_top_level(expression: str, separator: str) -> List[str]:
    depth = 0
    lowered = expression.lower()
    for index, char in enumerate(expression):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise MatrixError("unbalanced parentheses in color expression")
        elif depth == 0:
            if separator == " over ":
                match = re.match(r"\s+over\s+", expression[index:], re.IGNORECASE)
                if match:
                    return [expression[:index], expression[index + len(match.group(0)):]]
            elif lowered.startswith(separator, index):
                return [expression[:index], expression[index + len(separator):]]
    if depth:
        raise MatrixError("unbalanced parentheses in color expression")
    return [expression]


def resolve_color(expression: str, references: Mapping[str, Any] = None, stack: Tuple[str, ...] = ()) -> RGBA:
    """Resolve a CSS color, `A over B`, or `mix(A, B, t)` expression."""
    if not isinstance(expression, str):
        raise MatrixError("color expression must be a string")
    text = expression.strip()
    if not text:
        raise MatrixError("color expression must not be empty")
    parts = _split_top_level(text, " over ")
    if len(parts) == 2:
        if any(not part.strip() for part in parts):
            raise MatrixError("over expression requires foreground and background")
        return composite(resolve_color(parts[0], references, stack), resolve_color(parts[1], references, stack))
    if text.lower().startswith("mix(") and text.endswith(")"):
        body = text[4:-1]
        arguments = []
        remainder = body
        while len(arguments) < 2:
            split = _split_top_level(remainder, ",")
            if len(split) != 2:
                break
            arguments.append(split[0].strip())
            remainder = split[1]
        arguments.append(remainder.strip())
        if len(arguments) != 3 or any(not item for item in arguments):
            raise MatrixError("mix() requires three arguments")
        try:
            amount = float(arguments[2])
        except ValueError as exc:
            raise MatrixError("invalid mix amount: {!r}".format(arguments[2])) from exc
        if not math.isfinite(amount):
            raise MatrixError("mix amount must be finite")
        try:
            return mix(resolve_color(arguments[0], references, stack), resolve_color(arguments[1], references, stack), amount)
        except ColorError as exc:
            raise MatrixError(str(exc)) from exc
    if references is not None and text in references:
        if text in stack:
            cycle = " -> ".join(stack + (text,))
            raise MatrixError("cyclic background reference: {}".format(cycle))
        return resolve_color(references[text], references, stack + (text,))
    try:
        return parse_color(text)
    except ColorError as exc:
        if references is not None and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", text):
            raise MatrixError("unknown background reference {!r}".format(text)) from exc
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
        if not isinstance(name, str) or not name:
            raise MatrixError("threshold names must be non-empty strings")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise MatrixError("threshold {!r} must be a positive number".format(name))
        thresholds[name] = float(value)
    if level not in ("aa", "aaa"):
        raise MatrixError("level must be 'aa' or 'aaa'")
    if fail_under is not None and (not isinstance(fail_under, (int, float)) or isinstance(fail_under, bool) or not math.isfinite(fail_under) or fail_under <= 0):
        raise MatrixError("fail-under must be a positive finite number")
    if any(not isinstance(name, str) or not name for name in backgrounds):
        raise MatrixError("background names must be non-empty strings")
    resolved = {name: resolve_color(value, backgrounds, (name,)) for name, value in backgrounds.items()}
    results: List[Dict[str, Any]] = []
    seen = set()
    for token in tokens:
        if not isinstance(token, dict):
            raise MatrixError("each token must be an object")
        name, color, over_names = token.get("name"), token.get("color"), token.get("over")
        if not isinstance(name, str) or not name or name in seen:
            raise MatrixError("token names must be unique non-empty strings")
        seen.add(name)
        if not isinstance(over_names, list) or not over_names or any(not isinstance(item, str) or not item for item in over_names):
            raise MatrixError("token {!r} must list at least one background".format(name))
        base_level = token.get("level", "normal")
        threshold_name = "aaa_" + base_level if level == "aaa" and not str(base_level).startswith("aaa_") else str(base_level)
        if threshold_name not in thresholds:
            raise MatrixError("token {!r} uses unknown threshold {!r}".format(name, threshold_name))
        required = float(fail_under) if fail_under is not None else thresholds[threshold_name]
        foreground = resolve_color(color, backgrounds)
        pairs = []
        for background_name in sorted(set(over_names)):
            if background_name not in resolved:
                raise MatrixError("token {!r} references unknown background {!r}".format(name, background_name))
            background_rgba = resolved[background_name]
            background_rgb = over(background_rgba, (255.0, 255.0, 255.0))
            effective = over(foreground, background_rgb)
            ratio = contrast_ratio(effective, background_rgb)
            pairs.append({"background": background_name, "ratio": round(ratio, 6), "_raw_ratio": ratio})
        worst = min(pairs, key=lambda item: (item["_raw_ratio"], item["background"]))
        passed = worst["_raw_ratio"] >= required
        for pair in pairs:
            del pair["_raw_ratio"]
        results.append({"name": name, "level": threshold_name, "threshold": required, "passed": passed, "worst_background": worst["background"], "worst_ratio": worst["ratio"], "comparisons": pairs})
    results.sort(key=lambda item: item["name"])
    failures = sum(not item["passed"] for item in results)
    return {"wcag_version": "WCAG 2.x", "level": level, "token_count": len(results), "failure_count": failures, "passed": failures == 0, "results": results}
