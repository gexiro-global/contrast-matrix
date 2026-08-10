# Changelog

## [Unreleased]

- Bound build, runtime/optional, and development dependencies to tested next-major ceilings,
  and complete the package classifiers.
- Ship the inline type-information marker and explicit license-file metadata.
- Reject malformed, duplicate-key, non-finite, and ambiguous color/matrix inputs with clean
  input errors instead of coercing, crashing, or passing open.
- Resolve named, nested, and chained background expressions with cycle detection and correct
  alpha compositing.
- Compare full-precision contrast ratios at thresholds while retaining rounded display output.

## [0.1.0] - Initial release

- Add CSS color parsing, WCAG 2.x contrast math, matrix evaluation, and CI output formats.
