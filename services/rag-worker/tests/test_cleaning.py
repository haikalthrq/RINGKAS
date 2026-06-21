from __future__ import annotations

from ringkas_worker.cleaning import CleanedDocument, ConservativeTextCleaner, TextCleaner
from ringkas_worker.parsers import PdfPage, PdfPageMetadata, PdfParseResult


def page(number: int, text: str) -> PdfPage:
    return PdfPage(number, text, PdfPageMetadata(612.0, 792.0, 0))


def document(*pages: PdfPage) -> PdfParseResult:
    return PdfParseResult("parsed", tuple(pages))


def clean(*pages: PdfPage) -> CleanedDocument:
    return ConservativeTextCleaner().clean(document(*pages))


def test_normalizes_spaces_and_wrapped_lines() -> None:
    result = clean(page(1, "  Inflasi\t   tahunan\n\n Jakarta   3,50 %  "))
    assert result.pages[0].text == "Inflasi tahunan Jakarta 3,50 %"


def test_merges_clearly_split_hyphenated_word() -> None:
    result = clean(page(1, "per-\nubahan harga"))
    assert result.pages[0].text == "perubahan harga"


def test_preserves_wrapped_indonesian_reduplication() -> None:
    result = clean(page(1, "masing-\nmasing\ntahun-\ntahun\nsehari-\nhari\nrumah-\nrumah"))
    assert result.pages[0].text == "masing-masing tahun-tahun sehari-hari rumah-rumah"


def test_preserves_legitimate_hyphenated_term() -> None:
    result = clean(page(1, "Data sosial-ekonomi DKI Jakarta"))
    assert result.pages[0].text == "Data sosial-ekonomi DKI Jakarta"


def test_removes_repeated_header_across_pages() -> None:
    result = clean(
        page(1, "BPS PROVINSI DKI JAKARTA\nBab satu\nPenduduk 2024: 10.000 jiwa\nCatatan"),
        page(2, "BPS PROVINSI DKI JAKARTA\nBab dua\nPenduduk 2025: 10.100 jiwa\nCatatan"),
        page(3, "BPS PROVINSI DKI JAKARTA\nBab tiga\nPenduduk 2026: 10.200 jiwa\nCatatan"),
    )
    assert all("BPS PROVINSI" not in item.text for item in result.pages)
    assert [item.text for item in result.pages] == [
        "Bab satu Penduduk 2024: 10.000 jiwa",
        "Bab dua Penduduk 2025: 10.100 jiwa",
        "Bab tiga Penduduk 2026: 10.200 jiwa",
    ]


def test_removes_repeated_footer_only_when_repeated() -> None:
    result = clean(
        page(1, "Pembuka\nIsi halaman satu\nRincian satu\nSumber: BPS"),
        page(2, "Pembuka\nIsi halaman dua\nRincian dua\nSumber: BPS"),
        page(3, "Pembuka\nIsi halaman tiga\nRincian tiga\nCatatan metodologi penting"),
    )
    assert [item.text for item in result.pages] == [
        "Isi halaman satu Rincian satu",
        "Isi halaman dua Rincian dua",
        "Isi halaman tiga Rincian tiga Catatan metodologi penting",
    ]


def test_similar_substantive_lines_are_not_removed() -> None:
    result = clean(
        page(1, "Jumlah penduduk DKI Jakarta meningkat"),
        page(2, "Jumlah penduduk DKI Jakarta menurun"),
        page(3, "Jumlah penduduk DKI Jakarta stabil"),
    )
    assert all(item.text for item in result.pages)
    assert result.repeated_headers == ()
    assert result.repeated_footers == ()


def test_repeated_occurrences_on_one_page_do_not_qualify() -> None:
    result = clean(
        page(1, "Boilerplate\nBoilerplate\nIsi"),
        page(2, "Isi lain"),
    )
    assert result.repeated_headers == ()
    assert result.pages[0].text == "Boilerplate Boilerplate Isi"


def test_repeated_single_line_substantive_pages_remain_intact() -> None:
    result = clean(
        page(1, "Jumlah penduduk DKI Jakarta meningkat"),
        page(2, "Jumlah penduduk DKI Jakarta meningkat"),
    )
    assert [item.text for item in result.pages] == [
        "Jumlah penduduk DKI Jakarta meningkat",
        "Jumlah penduduk DKI Jakarta meningkat",
    ]


def test_two_line_edge_windows_cannot_erase_all_content() -> None:
    result = clean(page(1, "Sama\nSama"), page(2, "Sama\nSama"))
    assert result.pages[0].text == "Sama Sama"
    assert result.pages[1].text == "Sama Sama"


def test_ambiguous_header_and_footer_candidate_is_preserved() -> None:
    result = clean(
        page(1, "Sama\nIsi satu\nRincian satu\nSama"),
        page(2, "Sama\nIsi dua\nRincian dua\nSama"),
    )
    assert result.repeated_headers == ()
    assert result.repeated_footers == ()
    assert result.pages[0].text == "Sama Isi satu Rincian satu Sama"


def test_removes_only_matching_standalone_page_number() -> None:
    result = clean(page(1, "Penduduk 1.234 jiwa\n1"), page(2, "Tahun 2024: 2,50%\n2"))
    assert result.pages[0].text == "Penduduk 1.234 jiwa"
    assert result.pages[1].text == "Tahun 2024: 2,50%"


def test_preserves_numbers_units_years_periods_regions_and_definitions() -> None:
    source = "Indeks harga konsumen tahun 2024 sebesar 3,50% di DKI Jakarta per tahun."
    result = clean(page(1, source))
    assert result.pages[0].text == source


def test_preserves_page_number_and_metadata() -> None:
    original = page(7, "Judul Bagian\nTeks halaman")
    result = clean(original)
    assert result.pages[0].page_number == 7
    assert result.pages[0].metadata is original.metadata


def test_captures_conservative_heading_without_rewriting_text() -> None:
    result = clean(page(1, "Penduduk Menurut Wilayah\nJumlah penduduk 10 orang."))
    assert result.pages[0].section_heading == "Penduduk Menurut Wilayah"
    assert result.pages[0].text == "Penduduk Menurut Wilayah Jumlah penduduk 10 orang."


def test_empty_pages_are_retained() -> None:
    result = clean(page(1, ""), page(2, "   \n\t"))
    assert [(item.page_number, item.text, item.section_heading) for item in result.pages] == [
        (1, "", None),
        (2, "", None),
    ]


def test_cleaning_is_idempotent() -> None:
    first = clean(page(1, "Judul Bagian\nNilai 3,50%"))
    second = ConservativeTextCleaner().clean(
        PdfParseResult("parsed", tuple(page(item.page_number, item.text) for item in first.pages))
    )
    assert [(item.page_number, item.text) for item in second.pages] == [
        (item.page_number, item.text) for item in first.pages
    ]


def test_repeated_boilerplate_can_appear_on_only_some_pages() -> None:
    result = clean(
        page(1, "Laporan Tahunan BPS\nIsi pertama\nAkhir pertama"),
        page(2, "Isi kedua\nAkhir kedua"),
        page(3, "Laporan Tahunan BPS\nIsi ketiga\nAkhir ketiga"),
        page(4, "Isi keempat\nAkhir keempat"),
    )
    assert [item.text for item in result.pages] == [
        "Isi pertama Akhir pertama",
        "Isi kedua Akhir kedua",
        "Isi ketiga Akhir ketiga",
        "Isi keempat Akhir keempat",
    ]


def test_cleaner_protocol_is_implemented() -> None:
    assert isinstance(ConservativeTextCleaner(), TextCleaner)
