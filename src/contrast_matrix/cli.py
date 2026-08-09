"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .matrix import MatrixError, evaluate_matrix, load_matrix


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print("contrast-matrix: error: {}".format(message), file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="contrast-matrix", description="Check a WCAG contrast matrix.")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="evaluate a matrix file")
    check.add_argument("matrix", type=Path)
    check.add_argument("--format", choices=("table", "json", "sarif"), default="table")
    check.add_argument("--level", choices=("aa", "aaa"), default="aa")
    check.add_argument("--fail-under", type=float)
    return parser


def render_table(result: Mapping[str, Any]) -> str:
    rows = ["TOKEN  WORST BACKGROUND  RATIO  REQUIRED  RESULT"]
    for item in result["results"]:
        rows.append("{:<20} {:<20} {:>6.2f} {:>9.2f}  {}".format(item["name"], item["worst_background"], item["worst_ratio"], item["threshold"], "PASS" if item["passed"] else "FAIL"))
    rows.append("{} token(s), {} failure(s)".format(result["token_count"], result["failure_count"]))
    return "\n".join(rows)


def render_sarif(result: Mapping[str, Any], path: Path) -> Mapping[str, Any]:
    findings = []
    for item in result["results"]:
        if not item["passed"]:
            findings.append({"ruleId": "contrast-matrix/wcag-contrast", "level": "error", "message": {"text": "{} has worst-case contrast {:.2f}:1 over {} (required {:.2f}:1)".format(item["name"], item["worst_ratio"], item["worst_background"], item["threshold"])}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": str(path)}}}]})
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0", "runs": [{"tool": {"driver": {"name": "contrast-matrix", "informationUri": "https://github.com/gexiro-global/contrast-matrix", "rules": [{"id": "contrast-matrix/wcag-contrast", "shortDescription": {"text": "WCAG contrast threshold"}}]}}, "results": findings}]}


def main(argv: Sequence[str] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.fail_under is not None and args.fail_under <= 0:
        print("contrast-matrix: error: --fail-under must be positive", file=sys.stderr)
        return 2
    try:
        result = evaluate_matrix(load_matrix(args.matrix), args.level, args.fail_under)
    except MatrixError as exc:
        print("contrast-matrix: error: {}".format(exc), file=sys.stderr)
        return 2
    if args.format == "table":
        print(render_table(result))
    elif args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(render_sarif(result, args.matrix), indent=2, sort_keys=True))
    return 0 if result["passed"] else 1

