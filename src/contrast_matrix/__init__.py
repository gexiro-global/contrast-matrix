"""Public API for contrast-matrix."""

from .kernel import ColorError, WCAG_VERSION, contrast_ratio, mix, over, parse_color, relative_luminance
from .matrix import MatrixError, evaluate_matrix, load_matrix, resolve_color

__all__ = ["ColorError", "MatrixError", "WCAG_VERSION", "contrast_ratio", "evaluate_matrix", "load_matrix", "mix", "over", "parse_color", "relative_luminance", "resolve_color"]
__version__ = "0.1.0"

