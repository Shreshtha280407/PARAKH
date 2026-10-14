"""Independent integer-luma / Laplacian reference; no model, labels or threshold fitting."""
from __future__ import annotations
import math


def image_metrics(pixels: bytes, width: int, height: int) -> dict:
    if width < 1 or height < 1 or len(pixels) != width * height:
        raise ValueError('Invalid gray frame')
    lap = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            i = y * width + x
            lap.append(pixels[i - 1] + pixels[i + 1] + pixels[i - width] + pixels[i + width] - 4 * pixels[i])
    # Population variance via independent two-pass computation (Kotlin uses Welford).
    mean = sum(lap) / len(lap) if lap else None
    variance = sum((x - mean) ** 2 for x in lap) / len(lap) if lap else None
    return {'width': width, 'height': height, 'mean_luma': sum(pixels) / len(pixels),
            'dark_clip_fraction': sum(x <= 16 for x in pixels) / len(pixels),
            'highlight_clip_fraction': sum(x >= 235 for x in pixels) / len(pixels),
            'laplacian_variance': variance}


def assert_metrics(actual: dict, expected: dict, tolerance: float = 1e-6) -> None:
    for key, value in expected.items():
        observed = actual[key]
        if value is None:
            if observed is not None:
                raise AssertionError(f'{key}: expected unavailable, observed {observed}')
        elif observed is None or not math.isclose(value, observed, rel_tol=1e-9, abs_tol=tolerance):
            raise AssertionError(f'{key}: reference {value}, observed {observed}')
