"""#531: `workflow research` reads a page in the charset it names, as the WHATWG
Encoding Standard says (spec #505). Seam 1, the `workflow` CLI fed files and
`research.paragraphs`. The standard's own label table
(`tests/fixtures/research/whatwg-encodings.json`, its `encodings.json`, copied
verbatim) and its single-byte indexes (`whatwg-single-byte-indexes.json`, the
code points of `index-<name>.txt`) are what each test is checked against: a
label it doesn't list is refused, and a page is never decoded with a codec
outside it, nor with bytes replaced."""

import json
import time

import pytest

from conftest import KIT
from test_research_notes import (  # noqa: F401  (fixtures: project, server)
    NOTE,
    PAGE,
    URL,
    _check,
    _cli,
    _env,
    _h,
    _note,
    _snapshot,
    project,
    server,
)
from workflow import research

FIX = KIT / "tests/fixtures/research"
STANDARD = json.loads((FIX / "whatwg-encodings.json").read_text(encoding="utf-8"))
INDEXES = json.loads((FIX / "whatwg-single-byte-indexes.json").read_text(encoding="utf-8"))["indexes"]
LABELS = {label: e["name"] for group in STANDARD for e in group["encodings"] for label in e["labels"]}
NAMES = sorted({n for n in LABELS.values()})


# ---------- the standard's table ----------


def test_every_label_maps_to_the_encoding_the_standard_gives_it_and_no_other_label_maps():
    assert research.ENCODING_LABELS == LABELS


@pytest.mark.parametrize("label", sorted(LABELS))
def test_a_label_is_matched_whatever_its_case_and_the_white_space_around_it(label):
    assert research.encoding_named(label.upper()) == LABELS[label]
    assert research.encoding_named(f" \t{label}\n") == LABELS[label]


@pytest.mark.parametrize("label", ["punycode", "utf_8", "ascii\u0130", "\u212aoi8-r", "latin1\x00", ""])
def test_a_label_the_standard_doesnt_list_names_no_encoding(label):
    assert research.encoding_named(label) is None


def _index_of(name: str) -> list:
    return INDEXES["ISO-8859-8" if name == "ISO-8859-8-I" else name]


@pytest.mark.parametrize("name", sorted(set(INDEXES) | {"ISO-8859-8-I"}))
def test_a_single_byte_encoding_decodes_each_byte_as_the_standards_index(name):
    index = _index_of(name)
    for b in range(0x80):
        assert research.decode(bytes([b]), name) == chr(b)
    for b in range(0x80, 0x100):
        cp = index[b - 0x80]
        if cp is None:  # an error in the standard: refused, never a replacement character
            with pytest.raises(research.PageError, match=f"its bytes aren't valid {name}"):
                research.decode(bytes([0x41, b, 0x42]), name)
        else:
            assert research.decode(bytes([b]), name) == chr(cp), hex(b)


def test_x_user_defined_decodes_as_the_standard_says():
    raw = bytes(range(0x100))
    assert research.decode(raw, "x-user-defined") == "".join(chr(b) for b in range(0x80)) + "".join(
        chr(0xF780 + b - 0x80) for b in range(0x80, 0x100)
    )


def test_only_the_standards_multi_byte_encodings_use_a_python_codec_and_only_these():
    # GBK's decoder is gb18030's; Big5's covers HKSCS; Shift_JIS is Windows' (cp932); EUC-KR is Windows' (cp949)
    assert research.MULTI_BYTE_CODECS == {
        "UTF-8": "utf-8",
        "GBK": "gb18030",
        "gb18030": "gb18030",
        "Big5": "big5hkscs",
        "EUC-JP": "euc_jp",
        "ISO-2022-JP": "iso2022_jp",
        "Shift_JIS": "cp932",
        "EUC-KR": "cp949",
        "UTF-16BE": "utf-16-be",
        "UTF-16LE": "utf-16-le",
    }
    single = set(INDEXES) | {"ISO-8859-8-I", "x-user-defined"}
    assert set(research.MULTI_BYTE_CODECS) | single | {"replacement"} == set(NAMES)
    assert not set(research.MULTI_BYTE_CODECS) & single


# ---------- reading a page in its charset (seam 1) ----------

# (label, the page's text, its bytes): the bytes as a page in that charset holds them
_PAGES = [
    ("windows-1252", "Café menu – €12 “today”", "Café menu – €12 “today”".encode("cp1252")),
    ("ISO-8859-1", "Café", b"Caf\xe9"),
    ("latin1", "Café €5", b"Caf\xe9 \x805"),  # 0x80 is the euro sign: ISO-8859-1 reads as windows-1252
    ("Shift_JIS", "予約は30日前から ①", "予約は30日前から ①".encode("cp932")),
    ("MS932", "予約は30日前から", "予約は30日前から".encode("cp932")),
    ("ms_kanji", "予約は30日前から", "予約は30日前から".encode("cp932")),
    ("windows-31j", "予約は30日前から", "予約は30日前から".encode("cp932")),
    ("TIS-620", "จองโต๊ะล่วงหน้า 30 วัน", "จองโต๊ะล่วงหน้า 30 วัน".encode("cp874")),
    ("Big5-HKSCS", "訂座 \U000282e2", "訂座 \U000282e2".encode("big5hkscs")),
    ("big5", "訂座 \U000282e2", "訂座 \U000282e2".encode("big5hkscs")),
    ("EUC-KR", "예약 똠", "예약 똠".encode("cp949")),
    ("GBK", "预订 €", "预订 €".encode("gb18030")),
    ("gb18030", "预订 \U0001f600", "预订 \U0001f600".encode("gb18030")),
    ("EUC-JP", "予約", "予約".encode("euc_jp")),
    ("ISO-2022-JP", "予約", "予約".encode("iso2022_jp")),
    ("KOI8-R", "Бронь", "Бронь".encode("koi8_r")),
    ("windows-1251", "Бронь", "Бронь".encode("cp1251")),
    ("ISO-8859-2", "Rezervace na čtvrtek", "Rezervace na čtvrtek".encode("iso8859_2")),
    ("windows-1256", "حجز", "حجز".encode("cp1256")),
    ("ISO-8859-7", "Κράτηση", "Κράτηση".encode("iso8859_7")),
]
_IDS = [f"{label}-{i}" for i, (label, _, _) in enumerate(_PAGES)]


@pytest.mark.parametrize("label,text,raw", _PAGES, ids=_IDS)
def test_a_page_is_read_in_the_charset_its_header_names(label, text, raw):
    assert research.paragraphs(b"<p>" + raw + b"</p>", f"text/html; charset={label}") == [text]
    assert research.paragraphs(raw, f"text/plain; charset={label}") == [text]


@pytest.mark.parametrize("label,text,raw", _PAGES, ids=_IDS)
def test_a_page_is_read_in_the_charset_its_meta_names(label, text, raw):
    page = f'<!doctype html><html><head><meta charset="{label}"><title>t</title></head><body><p>'.encode() + raw + b"</p></body></html>"
    assert research.paragraphs(page, "text/html") == [text]
    old = f'<html><head><meta http-equiv="Content-Type" content="text/html; charset={label}"></head><body><p>'.encode() + raw + b"</p>"
    assert research.paragraphs(old, "text/html") == [text]


@pytest.mark.parametrize(
    "ctype",
    ["text/html; x-charset=utf-8; charset=windows-1252", "text/html;charset=windows-1252", "text/html; CHARSET=\"Windows-1252\""],
    ids=["after-another-parameter", "no-space", "quoted"],
)
def test_the_header_charset_is_its_charset_parameter(ctype):
    assert research.paragraphs(b"<p>Caf\xe9</p>", ctype) == ["Café"]


def test_a_parameter_ending_in_charset_names_no_charset():
    assert research.paragraphs(b"<p>Caf\xc3\xa9</p>", "text/html; x-charset=punycode") == ["Café"]


def test_a_thai_page_never_becomes_replacement_characters_and_two_words_never_hash_the_same():
    one, two = "จองโต๊ะ", "ยกเลิก"
    got = [research.paragraphs(f"<p>{w}</p>".encode("cp874"), "text/html; charset=tis-620") for w in (one, two)]
    assert got == [[one], [two]]
    assert "\ufffd" not in one + two
    assert _h(got[0][0]) != _h(got[1][0])


@pytest.mark.parametrize(
    "label,raw,name",
    [
        ("TIS-620", b"<p>\xa1\xdb</p>", "windows-874"),  # 0xDB isn't in windows-874
        ("TIS-620", b"<p>\xa1\xdc</p>", "windows-874"),
        ("Shift_JIS", b"<p>\x97</p>", "Shift_JIS"),  # a lead byte with no trail byte
        ("EUC-KR", b"<p>\xe5</p>", "EUC-KR"),
        ("Big5", b"<p>\xa4</p>", "Big5"),
        ("utf-16le", b"<\x00p\x00>", "UTF-16LE"),  # an odd number of bytes
        ("windows-1253", b"<p>\xaa</p>", "windows-1253"),
    ],
    ids=["tis-620-db", "tis-620-dc", "shift-jis-lead", "euc-kr-lead", "big5-lead", "utf-16-odd", "windows-1253-aa"],
)
def test_bytes_that_arent_valid_in_the_charset_are_refused_never_replaced(label, raw, name):
    with pytest.raises(research.PageError, match=f"its bytes aren't valid {name}"):
        research.paragraphs(raw, f"text/html; charset={label}")


@pytest.mark.parametrize(
    "label,raw,want",
    [
        ("ascii", b"<p>Caf\xc3\xa9 \x80</p>", "CafÃ© €"),
        ("us-ascii", b"<p>Caf\xc3\xa9 \x80</p>", "CafÃ© €"),
        ("ANSI_X3.4-1968", b"<p>\x80</p>", "€"),
        ("iso-8859-8-i", b"<p>\xf9\xec\xe5\xed</p>", "שלום"),
        ("logical", b"<p>\xf9\xec\xe5\xed</p>", "שלום"),
        ("windows-874", b"<p>\xa1\x80</p>", "ก€"),
        ("iso-8859-11", b"<p>\xa1</p>", "ก"),
        ("x-mac-roman", b"<p>\x8e</p>", "é"),
    ],
    ids=["ascii", "us-ascii", "ansi", "iso-8859-8-i", "logical", "windows-874", "iso-8859-11", "x-mac-roman"],
)
def test_labels_map_as_the_standard_says(label, raw, want):
    assert research.paragraphs(raw, f"text/html; charset={label}") == [want]


_NOT_LISTED = ["punycode", "unicode_escape", "raw_unicode_escape", "utf-7", "base64", "undefined", "idna", "rot13", "hex", "zlib", "utf_8", "cp65001", "u8", "646"]


@pytest.mark.parametrize("label", _NOT_LISTED)
def test_a_label_the_standard_doesnt_list_is_refused_from_the_header_or_the_meta(label):
    page = b"<p>Book up to 30 days ahead - call first. C:\\new</p>"
    why = f"it names a charset the Encoding Standard doesn't list \\({label}\\)"
    with pytest.raises(research.PageError, match=why):
        research.paragraphs(page, f"text/html; charset={label}")
    with pytest.raises(research.PageError, match=why):
        research.paragraphs(f'<meta charset="{label}">'.encode() + page, "text/html")
    with pytest.raises(research.PageError, match=why):
        research.paragraphs(page, f"text/plain; charset={label}")


def test_a_long_punycode_page_is_refused_at_once():
    t = time.monotonic()
    with pytest.raises(research.PageError, match="doesn't list"):
        research.paragraphs(b"<p>a-" + b"A" * 2_000_000 + b"</p>", "text/html; charset=punycode")
    assert time.monotonic() - t < 2


def test_a_long_label_is_cut_short_in_the_refusal():
    with pytest.raises(research.PageError) as e:
        research.paragraphs(b"<p>A</p>", "text/html; charset=" + "x" * 5000)
    assert len(str(e.value)) < 200 and str(e.value).endswith("…)")


@pytest.mark.parametrize("label", ["replacement", "iso-2022-kr", "hz-gb-2312", "iso-2022-cn", "csiso2022kr"])
def test_a_label_the_standard_reads_as_one_replacement_character_is_refused(label):
    with pytest.raises(research.PageError, match=f"it is in {label}, which the Encoding Standard reads as one replacement character"):
        research.paragraphs(b"<p>A</p>", f"text/html; charset={label}")


# ---------- byte order marks, and what a <meta> can't name ----------


@pytest.mark.parametrize(
    "ctype,raw",
    [
        ("text/html; charset=windows-1252", b"\xef\xbb\xbf<p>Caf\xc3\xa9</p>"),
        ("text/html; charset=shift_jis", b"\xef\xbb\xbf<p>Caf\xc3\xa9</p>"),
        ("text/html", b"\xff\xfe" + "<p>Café</p>".encode("utf-16-le")),
        ("text/html; charset=windows-1252", b"\xfe\xff" + "<p>Café</p>".encode("utf-16-be")),
        ("text/html; charset=utf-16be", b"\xff\xfe" + "<p>Café</p>".encode("utf-16-le")),
        ("text/plain", b"\xff\xfe" + "Café".encode("utf-16-le")),
    ],
    ids=["utf8-bom-over-header", "utf8-bom-over-shift-jis", "utf16le-bom", "utf16be-bom-over-header", "utf16le-bom-over-utf16be", "plain-text-utf16le-bom"],
)
def test_a_byte_order_mark_wins_over_the_label(ctype, raw):
    assert research.paragraphs(raw, ctype) == ["Café"]


def test_a_utf16_page_named_by_its_header_is_read():
    assert research.paragraphs("<p>Café</p>".encode("utf-16-le"), "text/html; charset=utf-16") == ["Café"]
    assert research.paragraphs("<p>Café</p>".encode("utf-16-be"), "text/html; charset=utf-16be") == ["Café"]


@pytest.mark.parametrize(
    "label,raw,want",
    [
        ("utf-16", b"<p>Caf\xc3\xa9</p>", "Café"),  # a <meta> readable as ASCII isn't UTF-16: read as UTF-8
        ("utf-16be", b"<p>Caf\xc3\xa9</p>", "Café"),
        ("x-user-defined", b"<p>Caf\xe9</p>", "Café"),  # read as windows-1252
    ],
    ids=["utf-16", "utf-16be", "x-user-defined"],
)
def test_a_meta_naming_utf16_or_x_user_defined_is_read_as_html_says(label, raw, want):
    assert research.paragraphs(f'<meta charset="{label}">'.encode() + raw, "text/html") == [want]


# ---------- a page with no content type (#527's handling kept) ----------


@pytest.mark.parametrize("label", ["windows-1252", "us-ascii", "shift_jis", "koi8-r"])
def test_a_page_with_no_content_type_in_a_charset_is_read_when_it_reads_the_same_in_utf8(label):
    raw = b"<!doctype html><html><head><title>t</title></head><body><p>Book ahead.</p></body></html>"
    assert research.paragraphs(raw, f"; charset={label}") == ["Book ahead."]
    meta = raw.replace(b"<title>", f'<meta charset="{label}"><title>'.encode())
    assert research.paragraphs(meta, "") == ["Book ahead."]


@pytest.mark.parametrize(
    "ctype,raw",
    [
        ("; charset=windows-1252", b"<!doctype html><p>Caf\xc3\xa9</p>"),  # valid UTF-8, but not the same text in windows-1252
        ("", b'<!doctype html><meta charset="windows-1252"><p>Caf\xc3\xa9</p>'),
        ("; charset=us-ascii", "First \u00c1.\n".encode()),  # 0x81 in windows-1252 is a control character
        ("; charset=windows-1252", b"<!doctype html><p>Caf\xe9</p>"),  # not valid UTF-8: as #527 left it
        ("; charset=utf-16le", b"<!doctype html><p>A</p>"),
    ],
    ids=["header", "meta", "control-in-windows-1252", "not-utf8", "utf-16"],
)
def test_a_page_with_no_content_type_that_reads_differently_in_its_charset_is_refused(ctype, raw):
    with pytest.raises(research.PageError, match="no content type"):
        research.paragraphs(raw, ctype)


# ---------- UTF-8 pages read exactly as before ----------


def test_the_fixture_pages_fingerprints_are_unchanged_whatever_utf8_label_it_names():
    want = (NOTE / "sources/booking-help.fingerprints").read_text(encoding="utf-8").splitlines()[1:]
    for ctype in ("text/html", "text/html; charset=utf-8", "text/html; charset=UTF8", "text/html; charset=unicode-1-1-utf-8"):
        got = research.paragraphs(PAGE.read_bytes(), ctype)
        assert [f"{i} {_h(t)}" for i, t in enumerate(got, 1)] == want


# ---------- the CLI ----------


def test_fingerprint_reads_a_saved_page_in_shift_jis_by_its_meta(project, tmp_path):
    page = tmp_path / "yoyaku.html"
    page.write_bytes('<!doctype html><html><head><meta charset="Shift_JIS"><title>t</title></head><body><p>予約は30日前から</p></body></html>'.encode("cp932"))
    p = _cli("fingerprint", URL, "--page", page, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [(x["text"], x["hash"]) for x in json.loads(p.stdout)["paragraphs"]] == [("予約は30日前から", _h("予約は30日前から"))]


def test_fingerprint_fetches_a_thai_page_by_its_header(project, server):
    base, routes = server
    routes["/th"] = (200, "text/html; charset=TIS-620", "<p>จองโต๊ะล่วงหน้า</p><p>ยกเลิก</p>".encode("cp874"))
    p = _cli("fingerprint", f"{base}/th", "--fetch", "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)["paragraphs"]
    assert [x["text"] for x in got] == ["จองโต๊ะล่วงหน้า", "ยกเลิก"]
    assert got[0]["hash"] != got[1]["hash"]


def test_fingerprint_refuses_a_label_the_standard_doesnt_list_and_writes_nothing(project, tmp_path):
    page = tmp_path / "menu.html"
    page.write_bytes(b'<meta charset="punycode"><p>Book up to 30 days ahead - call first.</p>')
    before = _snapshot(project)
    p = _cli("fingerprint", URL, "--page", page, env=_env(project))
    assert p.returncode == 1 and p.stdout == ""
    assert "can't read" in p.stderr and "it names a charset the Encoding Standard doesn't list (punycode)" in p.stderr
    assert "Traceback" not in p.stderr
    assert _snapshot(project) == before


def test_check_reads_a_source_served_in_windows_1252(project, server):
    base, routes = server
    link = f"{base}/help/booking"
    routes["/help/booking"] = (200, "text/html; charset=windows-1252", PAGE.read_bytes())  # the fixture page is ASCII
    folder = _note(project).parent
    for f in ("note.md", "sources/booking-help.md", "sources/booking-help.fingerprints"):
        (folder / f).write_text((folder / f).read_text().replace(URL, link))
    p = _check(project, extra=["--fetch"])
    assert p.returncode == 0, p.stderr
    (src,) = json.loads(p.stdout)["sources"]
    assert src["result"] == "unchanged", src
