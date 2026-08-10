# contrast-matrix

[![CI](https://github.com/gexiro-global/contrast-matrix/actions/workflows/ci.yml/badge.svg)](https://github.com/gexiro-global/contrast-matrix/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/contrast-matrix.svg)](https://pypi.org/project/contrast-matrix/)
[![Python](https://img.shields.io/pypi/pyversions/contrast-matrix.svg)](https://pypi.org/project/contrast-matrix/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

A CI-first WCAG color-contrast matrix checker for design tokens, with no browser or network required.

## Quickstart

```bash
pip install "contrast-matrix[yaml]"
contrast-matrix check examples/matrix.yaml
contrast-matrix check examples/matrix.yaml --format sarif --level aaa
```

JSON support uses only the Python standard library. Install `contrast-matrix[yaml]` to read YAML.
The exit status is `0` when every token passes, `1` when any token fails, and `2` for usage or
input errors.

## Input schema

The root object has `backgrounds`, `tokens`, and an optional `thresholds` map:

```yaml
thresholds: {normal: 4.5, large: 3.0, aaa_normal: 7.0}
backgrounds:
  surface: "#ffffff"
  surface-alt: "#f4f4f5"
  overlay: "rgba(0,0,0,0.6) over #3b82f6"
tokens:
  - name: text-primary
    color: "#18181b"
    over: [surface, surface-alt]
    level: normal
  - name: text-on-overlay
    color: "rgba(255,255,255,0.9)"
    over: [overlay]
    level: large
```

Background keys are arbitrary names. Colors accept CSS `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`,
`rgb()`, `rgba()`, `hsl()`, and `hsla()`. Derived expressions accept `foreground over background`
and `mix(first, second, t)`, where `t` ranges from 0 to 1. Each token requires a unique `name`, a
`color`, a non-empty `over` list of background names, and a threshold `level`. Built-ins are
`normal` (4.5), `large` (3.0), `aaa_normal` (7.0), and `aaa_large` (4.5); the threshold map can add
or override names. `--level aaa` maps `normal` and `large` to their AAA counterparts, while
`--fail-under N` overrides every token's threshold.

Derived expressions may use background names as operands (for example,
`rgba(0,0,0,.5) over surface`); references may be nested or chained, and unknown or cyclic
references are rejected as input errors.

## Why a matrix?

Pairwise checkers answer whether one foreground works on one background. Design tokens often render
on several surfaces, including translucent and derived colors. This tool evaluates every declared
pair and reports the minimum ratio and the background that produced it, making the worst case an
explicit, deterministic CI result.

The calculation follows **WCAG 2.x**: sRGB channels are linearized, relative luminance uses the
0.2126/0.7152/0.0722 coefficients, and contrast is `(Llight + 0.05) / (Ldark + 0.05)`. Alpha
foregrounds are composited before comparison. This implements the WCAG 2.x contrast formula; it is
not an APCA/WCAG 3 implementation.

## Output

`--format table` prints a compact summary. `json` emits the complete sorted result, including all
pairs. `sarif` emits SARIF 2.1.0 findings for failed tokens. Inputs, tokens, backgrounds, and JSON
keys are ordered deterministically so repeated runs produce clean diffs. See [examples](examples/).

## Development

```bash
python -m pip install -e '.[dev]'
pytest -q
```

## License

[Apache-2.0](LICENSE).

Built and maintained by [Gexiro Global Enterprises Ltd](https://gexiro.com).

Part of the [Gexiro open-source toolkit](https://github.com/gexiro-global).
