"""#531: `workflow research` reads a page in the charset it names, as the WHATWG
Encoding Standard says (spec #505). Seam 1, the `workflow` CLI fed files and
`research.paragraphs`. The standard's own label table
(`tests/fixtures/research/whatwg-encodings.json`, its `encodings.json`, copied
verbatim) and its single-byte indexes (`whatwg-single-byte-indexes.json`, the
code points of `index-<name>.txt`) are what each test is checked against: a
label it doesn't list is refused, and a page is never decoded with a codec
outside it, nor with bytes replaced."""

import hashlib
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
    # Shift_JIS is Windows' (cp932); EUC-KR is Windows' (cp949)
    assert research.MULTI_BYTE_CODECS == {
        "UTF-8": "utf-8",
        "Shift_JIS": "cp932",
        "EUC-KR": "cp949",
        "UTF-16BE": "utf-16-be",
        "UTF-16LE": "utf-16-le",
    }
    # the standard's own decoders, GBK's being gb18030's and Big5's covering HKSCS, with indexes built from these codecs
    assert set(research.MULTI_BYTE_DECODERS) == {"GBK", "gb18030", "Big5", "EUC-JP", "ISO-2022-JP"}
    assert research.INDEX_CODECS == {"gb18030": "gb18030", "big5": "big5hkscs", "jis0208": "cp932", "jis0212": "euc_jp"}
    single = set(INDEXES) | {"ISO-8859-8-I", "x-user-defined"}
    decoders = set(research.MULTI_BYTE_DECODERS)
    assert set(research.MULTI_BYTE_CODECS) | decoders | single | {"replacement"} == set(NAMES)
    assert not set(research.MULTI_BYTE_CODECS) & (decoders | single) and not decoders & single



# ---------- the multi-byte decoders: the standard's own indexes ----------

# The standard's multi-byte indexes this kit builds (`whatwg-multi-byte-indexes.json`):
# each one's number of entries and the SHA-256 of its entries, and index gb18030 ranges whole.
MULTI = json.loads((FIX / "whatwg-multi-byte-indexes.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(MULTI["indexes"]))
def test_a_multi_byte_index_is_the_standards_own(name):
    index = research.multi_byte_index(name)
    entries = "".join(f"{p}\t0x{ord(c):04X}\n" for p, c in sorted(index.items()))
    assert len(index) == MULTI["indexes"][name]["entries"]
    assert hashlib.sha256(entries.encode()).hexdigest() == MULTI["indexes"][name]["sha256"]


def _gb18030_ranges_code_point(pointer: int) -> int | None:
    """The standard's "index gb18030 ranges code point"."""
    if 39419 < pointer < 189000 or pointer > 1237575:
        return None
    if pointer == 7457:
        return 0xE7C7
    offset, code_point = max(r for r in MULTI["gb18030-ranges"] if r[0] <= pointer)
    return code_point + pointer - offset


def _gb18030_four_bytes(pointer: int) -> bytes:
    pointer, b4 = divmod(pointer, 10)
    pointer, b3 = divmod(pointer, 126)
    b1, b2 = divmod(pointer, 10)
    return bytes([b1 + 0x81, b2 + 0x30, b3 + 0x81, b4 + 0x30])


@pytest.mark.parametrize("name", ["gb18030", "GBK"])
def test_gb18030_reads_four_bytes_as_the_standards_ranges_say(name):
    pointers = [*range(0, 39430), *range(188990, 1237586, 97), *range(1237570, 1237586), 1587599]
    for pointer in pointers:
        raw, want = _gb18030_four_bytes(pointer), _gb18030_ranges_code_point(pointer)
        if want is None:
            with pytest.raises(research.PageError, match=f"its bytes aren't valid {name}"):
                research.decode(raw, name)
        else:
            assert research.decode(raw, name) == chr(want), (pointer, raw.hex())


@pytest.mark.parametrize("label", ["GBK", "gb2312", "gb18030"])
def test_gbk_reads_0x80_as_the_euro_sign(label):
    raw = "价格：".encode("gb18030") + b"\x80" + b"100"
    assert research.paragraphs(b"<p>" + raw + b"</p>", f"text/html; charset={label}") == ["价格：€100"]


@pytest.mark.parametrize(
    "raw,want",
    [(b"\xa3\xa0", "\u3000"), (b"\xa6\xd9", "\ufe10"), (b"\xa6\xdf", "\ufe16"), (b"\xa8\xbc", "\u1e3f"), (b"\xfe\x59", "\u9fb4")],
    ids=["a3a0", "a6d9", "a6df", "a8bc", "fe59"],
)
def test_gbk_reads_two_bytes_as_the_standards_index(raw, want):
    assert research.decode(raw, "GBK") == want


@pytest.mark.parametrize("raw", [b"\xff", b"\x81", b"\x81\x7f", b"\x81\xff", b"\x81\x30", b"\x81\x30\x81", b"\x81\x30\x7f\x30", b"\x81\x30\x81\x7f"])
def test_gbk_refuses_bytes_the_standard_doesnt_define(raw):
    with pytest.raises(research.PageError, match="its bytes aren't valid GBK"):
        research.decode(b"A" + raw, "GBK")



@pytest.mark.parametrize("label", ["Big5-HKSCS", "big5"])
def test_big5_reads_an_hkscs_character_with_leading_byte_0x87(label):
    assert research.paragraphs(b"<p>HKSCS \x87\x7a</p>", f"text/html; charset={label}") == ["HKSCS \u3875"]


def test_big5_never_reads_two_different_codes_as_one_character():
    # 0xA1 0xFE is U+FF0F and 0xA2 0x41 is U+2215 in the standard's index
    one, two = research.decode(b"\xa1\xfe", "Big5"), research.decode(b"\xa2\x41", "Big5")
    assert (one, two) == ("\uff0f", "\u2215")
    assert _h(one) != _h(two)


@pytest.mark.parametrize(
    "raw,want",
    [(b"\xa1\x45", "\u2027"), (b"\xa1\xc2", "\u00af"), (b"\xa3\xe1", "\u20ac"), (b"\x88\x62", "\u00ca\u0304"), (b"\x88\xa5", "\u00ea\u030c")],
    ids=["a145", "a1c2", "a3e1", "8862-two-code-points", "88a5-two-code-points"],
)
def test_big5_reads_two_bytes_as_the_standard_says(raw, want):
    assert research.decode(raw, "Big5") == want


@pytest.mark.parametrize("raw", [b"\x80", b"\xff", b"\x81", b"\x81\x40", b"\xa4\x7f", b"\xa4\xa0", b"\xa4\xff"])
def test_big5_refuses_bytes_the_standard_doesnt_define(raw):
    with pytest.raises(research.PageError, match="its bytes aren't valid Big5"):
        research.decode(b"A" + raw, "Big5")



def test_euc_jp_reads_nec_row_13():
    raw = "手順".encode("euc_jp") + b"\xad\xa1" + "を見て".encode("euc_jp")
    assert research.paragraphs(b"<p>" + raw + b"</p>", "text/html; charset=EUC-JP") == ["手順①を見て"]


def test_euc_jp_reads_a_wave_dash_as_shift_jis_does_so_the_same_text_hashes_the_same():
    assert research.decode(b"\xa1\xc1", "EUC-JP") == research.decode(b"\x81\x60", "Shift_JIS") == "\uff5e"


@pytest.mark.parametrize(
    "raw,want",
    [
        (b"\xa1\xc2", "\u2225"),
        (b"\xa1\xdd", "\uff0d"),
        (b"\xa1\xf1", "\uffe0"),
        (b"\xa1\xf2", "\uffe1"),
        (b"\xa2\xcc", "\uffe2"),
        (b"\xf9\xa1", "\u7e8a"),  # IBM's extensions, leading bytes 0xF9 to 0xFC
        (b"\x8e\xa1", "\uff61"),  # halfwidth katakana
        (b"\x8f\xb0\xa1", "\u4e02"),  # JIS X 0212
        (b"\x8f\xa2\xb7", "\uff5e"),
    ],
    ids=["a1c2", "a1dd", "a1f1", "a1f2", "a2cc", "ibm-f9a1", "katakana", "jis0212", "jis0212-a2b7"],
)
def test_euc_jp_reads_its_bytes_as_the_standard_says(raw, want):
    assert research.decode(raw, "EUC-JP") == want


@pytest.mark.parametrize("raw", [b"\x80", b"\xff", b"\xa1", b"\xa1\x41", b"\x8e\xe0", b"\x8f\xa1", b"\x8f\xa1\x41", b"\xa9\xa1"])
def test_euc_jp_refuses_bytes_the_standard_doesnt_define(raw):
    with pytest.raises(research.PageError, match="its bytes aren't valid EUC-JP"):
        research.decode(b"A" + raw, "EUC-JP")


@pytest.mark.parametrize(
    "raw,want",
    [
        (b"\x1b(I\x21\x5f\x1b(B", "\uff61\uff9f"),  # halfwidth katakana
        (b"\x1b$B\x2d\x21\x1b(B", "\u2460"),  # NEC row 13
        (b"\x1b$@\x30\x21\x1b(B", "\u4e9c"),
        (b"\x1b(J\x5c\x7e\x1b(BA", "\u00a5\u203eA"),  # Roman
    ],
    ids=["katakana", "row-13", "jis-1978", "roman"],
)
def test_iso_2022_jp_reads_its_escapes_as_the_standard_says(raw, want):
    assert research.decode(raw, "ISO-2022-JP") == want
    assert research.paragraphs(b"<p>" + raw + b"</p>", "text/html; charset=iso-2022-jp") == [want]


@pytest.mark.parametrize(
    "raw",
    [
        b"\x1b$B\x1b(B",  # an escape right after another
        b"a\x0eb",  # SO and SI in ASCII
        b"a\x0fb",
        b"a\x80",
        b"\x1b$A",  # an escape the standard doesn't list
        b"a\x1b",
        b"\x1b$B\x30",  # a leading byte with no trailing one
        b"\x1b$B\x30\x1b(B",
        b"\x1b$B\x29\x21",  # a code its index leaves undefined
        b"\x1b(I\x60",
    ],
    ids=["two-escapes", "so", "si", "not-ascii", "unknown-escape", "escape-at-end", "lead-at-end", "escape-as-trail", "undefined", "katakana-range"],
)
def test_iso_2022_jp_refuses_bytes_the_standard_doesnt_define(raw):
    with pytest.raises(research.PageError, match="its bytes aren't valid ISO-2022-JP"):
        research.decode(raw, "ISO-2022-JP")


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


_UTF8_PAGE = "<p>Café — 日本</p>".encode()


@pytest.mark.parametrize(
    "before",
    [
        b'<!-- old: <meta charset="windows-1252"> -->',
        b'<!-- <meta charset="windows-1252"> -->',
        b'<script>document.write("<meta charset=koi8-r>")</script>',
        b'<SCRIPT type="text/javascript">var m = \'<meta charset="windows-1252">\';</SCRIPT>',
        b'<meta data-charset="windows-1252">',
        b'<meta name="description" content="Set charset=windows-1252 in your editor">',
        b'<meta name="x" content="text/html; charset=latin1">',
        b'<div title=\'<meta charset="windows-1252">\'></div>',
    ],
    ids=["comment", "comment-only", "script", "script-upper", "data-charset", "description", "content-no-http-equiv", "in-an-attribute"],
)
def test_a_meta_in_a_comment_a_script_or_another_attribute_or_content_without_http_equiv_names_no_charset(before):
    # with no other <meta>, the page is read as UTF-8; with a real one after it, in that one's charset
    assert research.paragraphs(before + _UTF8_PAGE, "text/html") == ["Café — 日本"]
    assert research.paragraphs(before + b'<meta charset="utf-8">' + _UTF8_PAGE, "text/html") == ["Café — 日本"]
    assert research.paragraphs(before + b'<meta charset="windows-1252">' + b"<p>Caf\xe9</p>", "text/html") == ["Café"]


@pytest.mark.parametrize(
    "meta",
    [
        b"<meta charset=windows-1252>",
        b"<META CHARSET='Windows-1252'/>",
        b'<meta\ncharset = "windows-1252">',
        b'<meta content="text/html; charset=windows-1252" http-equiv="Content-Type">',
        b"<meta http-equiv=content-type content='text/html;charset = \"windows-1252\"'>",
        b'<!--><meta charset="windows-1252">',  # "<!-->" is a whole comment
        b'<script></script><meta charset="windows-1252">',
    ],
    ids=["unquoted", "upper-case", "spaces", "content-first", "content-quoted-label", "empty-comment", "after-a-script"],
)
def test_a_meta_charset_outside_comments_and_scripts_is_read(meta):
    assert research.paragraphs(meta + b"<p>Caf\xe9</p>", "text/html") == ["Café"]


_NO_ENCODING_METAS = [
    b'<meta charset="">',
    b"<meta charset>",
    b"<meta charset=''>",
    b'<meta charset=" ">',
    b"<meta charset=utf-8/>",
    b'<meta charset="utf-8;">',
    b'<meta charset=""utf-8"">',
    b'<meta charset="{{charset}}">',
    b'<meta charset="punycode">',
    b'<meta charset="caf\xc3\xa9">',
    b'<meta http-equiv="Content-Type" content="text/html; charset=utf-8, text/html">',
    b'<meta http-equiv="Content-Type" content="text/html; charset=">',
]
_NO_ENCODING_IDS = ["empty", "bare", "empty-single-quotes", "blank", "slash", "semicolon", "doubled-quotes", "template", "punycode", "not-ascii", "content-list", "content-empty"]


@pytest.mark.parametrize("meta", _NO_ENCODING_METAS, ids=_NO_ENCODING_IDS)
def test_a_meta_whose_label_names_no_encoding_is_passed_over_as_htmls_prescan_does(meta):
    # with no other label, the page is read as UTF-8, strictly
    assert research.paragraphs(meta + b"<p>Caf\xc3\xa9</p>", "text/html") == ["Café"]
    with pytest.raises(research.PageError, match="its bytes aren't valid UTF-8"):
        research.paragraphs(meta + b"<p>Caf\xe9</p>", "text/html")
    # the search goes on: a later <meta> naming a label the standard lists is read
    assert research.paragraphs(meta + b'<meta charset="utf-8"><p>Caf\xc3\xa9</p>', "text/html") == ["Café"]
    assert research.paragraphs(meta + b'<meta charset="windows-1252"><p>Caf\xe9</p>', "text/html") == ["Café"]


def test_fingerprint_and_check_read_a_utf8_page_whose_meta_names_no_encoding(project, tmp_path):
    page = tmp_path / "booking-help.html"
    page.write_bytes(PAGE.read_bytes().replace(b'<meta charset="utf-8">', b"<meta charset=utf-8/>"))
    p = _cli("fingerprint", URL, "--page", page, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    want = (NOTE / "sources/booking-help.fingerprints").read_text(encoding="utf-8").splitlines()[1:]
    assert [f"{x['position']} {x['hash']}" for x in json.loads(p.stdout)["paragraphs"]] == want
    p = _check(project, (URL, page))
    assert p.returncode == 0, p.stderr
    (src,) = json.loads(p.stdout)["sources"]
    assert src["result"] == "unchanged", src


def test_fingerprint_reads_a_utf8_page_whose_comment_names_another_charset(project, tmp_path):
    page = tmp_path / "menu.html"
    page.write_bytes(
        '<!doctype html><html><head><!-- old: <meta charset="windows-1252"> --><meta charset="utf-8"><title>t</title></head>'
        "<body><p>Café — 日本</p></body></html>".encode()
    )
    p = _cli("fingerprint", URL, "--page", page, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [x["text"] for x in json.loads(p.stdout)["paragraphs"]] == ["Café — 日本"]


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


@pytest.mark.parametrize("byte", [0xA0, 0xFD, 0xFE, 0xFF])
def test_a_shift_jis_byte_the_standard_leaves_undefined_is_refused_never_read_as_a_private_use_character(byte):
    # Windows' cp932 reads 0xA0 and 0xFD to 0xFF as U+F8F0 to U+F8F3; the standard's Shift_JIS decoder refuses them
    for raw in (b"<p>" + bytes([byte]) + b"</p>", b"<p>x" + bytes([byte]) + b"y</p>"):
        with pytest.raises(research.PageError, match="its bytes aren't valid Shift_JIS"):
            research.paragraphs(raw, "text/html; charset=shift_jis")


def test_shift_jis_reads_each_byte_alone_as_the_standard_says():
    for b in range(0x100):
        if b <= 0x80:
            assert research.decode(bytes([b]), "Shift_JIS") == chr(b)
        elif 0xA1 <= b <= 0xDF:  # halfwidth katakana
            assert research.decode(bytes([b]), "Shift_JIS") == chr(0xFF61 - 0xA1 + b)
        else:  # 0xA0 and 0xFD to 0xFF, and a leading byte with nothing after it
            with pytest.raises(research.PageError, match="its bytes aren't valid Shift_JIS"):
                research.decode(bytes([b]), "Shift_JIS")
    # 0xA0 and 0xFC as a trailing byte are still read
    assert research.decode(b"\x81\xa0\x88\xfc", "Shift_JIS") == "□蔭"


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
def test_a_label_the_standard_doesnt_list_is_refused_from_the_header_and_passed_over_in_a_meta(label):
    page = b"<p>Book up to 30 days ahead - call first. C:\\new</p>"
    why = f"it names a charset the Encoding Standard doesn't list \\({label}\\)"
    with pytest.raises(research.PageError, match=why):
        research.paragraphs(page, f"text/html; charset={label}")
    with pytest.raises(research.PageError, match=why):
        research.paragraphs(page, f"text/plain; charset={label}")
    # a <meta> naming it is passed over, as HTML's prescan does: the page is read as UTF-8, never in it
    assert research.paragraphs(f'<meta charset="{label}">'.encode() + page, "text/html") == ["Book up to 30 days ahead - call first. C:\\new"]


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


def test_fingerprint_refuses_a_label_the_standard_doesnt_list_and_writes_nothing(project, server):
    base, routes = server
    routes["/menu"] = (200, "text/html; charset=punycode", b"<p>Book up to 30 days ahead - call first.</p>")
    before = _snapshot(project)
    p = _cli("fingerprint", f"{base}/menu", "--fetch", env=_env(project))
    assert p.returncode == 1 and p.stdout == ""
    assert "can't fetch" in p.stderr and "it names a charset the Encoding Standard doesn't list (punycode)" in p.stderr
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


# ---------- the changelog ----------


def _note_531() -> tuple[str, str]:
    """The #531 note's body and its "For projects updating" line, each on one line."""
    from changelog_notes import since_0110

    log = since_0110()
    start = log.rfind("\n\n", 0, log.index("(#531,")) + 2
    body, rest = log[start:].split("\n\n", 1)
    updating = rest.split("\n\n", 1)[0]
    assert updating.startswith("- **For projects updating:**")
    return " ".join(body.split()), " ".join(updating.split())


def test_the_changelog_says_which_sources_fingerprinted_before_now_cant_be_fetched():
    # a page served with no content type naming `us-ascii`, whose bytes are UTF-8, and a label in Python's
    # own spelling, were read as UTF-8 before; now `check` says can't fetch
    for ctype in ("; charset=us-ascii", "text/html; charset=utf_8", "text/html; charset=cp65001"):
        with pytest.raises(research.PageError):
            research.paragraphs("<!doctype html><p>Café</p>".encode(), ctype)
    _, updating = _note_531()
    assert "can't fetch" in updating
    assert "no content type" in updating
    assert "`utf_8`" in updating and "`cp65001`" in updating


def test_the_changelog_says_a_utf8_page_reads_as_before_only_by_a_label_the_standard_lists():
    body, _ = _note_531()
    (sentence,) = [s for s in body.split(". ") if "exactly as before" in s]
    assert "the standard lists" in sentence


def test_the_changelog_says_a_meta_label_the_standard_doesnt_list_is_passed_over_and_only_the_headers_is_refused():
    # a UTF-8 page whose <meta> reads `charset=utf-8/` or `charset=""` read before and still reads
    for raw in (b"<meta charset=utf-8/><p>Caf\xc3\xa9</p>", b'<meta charset=""><p>Caf\xc3\xa9</p>', b'<meta charset="utf_8"><p>Caf\xc3\xa9</p>'):
        assert research.paragraphs(raw, "text/html") == ["Café"]
    body, updating = _note_531()
    (sentence,) = [s for s in body.split(". ") if "It stays refused" in s]
    assert "the header's label is one the standard doesn't list" in sentence
    assert "A `<meta>` whose label the standard doesn't list, an empty one among them, is passed over" in body
    assert "One whose header names a label in Python's own spelling" in updating
