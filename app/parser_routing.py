"""Domain-neutral page-quality decisions shared by parser backends and evals."""

from __future__ import annotations


def requires_local_ocr(
    reasons: list[str],
    *,
    native_text_length: int,
    is_garbled: bool,
) -> bool:
    """Route only strong native-text failures to local OCR.

    LiteParse intentionally reports broad complexity signals. Sparse text and
    embedded images alone do not make native text unusable, and vector text is
    an OCR trigger only when the usable native layer is nearly absent.
    """

    observed = set(reasons)
    return bool(
        {"scanned", "no-text"}.intersection(observed)
        or is_garbled
        or ("vector-text" in observed and native_text_length < 80)
    )
