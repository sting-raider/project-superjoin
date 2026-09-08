from app.parser_routing import requires_local_ocr


def test_selective_ocr_requires_a_strong_unresolved_native_signal() -> None:
    assert requires_local_ocr(["scanned"], native_text_length=0, is_garbled=False)
    assert requires_local_ocr(["no-text"], native_text_length=0, is_garbled=False)
    assert requires_local_ocr(["garbled"], native_text_length=500, is_garbled=True)
    assert requires_local_ocr(["vector-text"], native_text_length=20, is_garbled=False)


def test_selective_ocr_keeps_usable_native_pages_on_the_fast_path() -> None:
    assert not requires_local_ocr(
        ["sparse-text", "embedded-images"],
        native_text_length=50,
        is_garbled=False,
    )
    assert not requires_local_ocr(
        ["vector-text"],
        native_text_length=4000,
        is_garbled=False,
    )
