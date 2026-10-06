"""Post matnidagi HTML teglar va Telegram tugmalari joylashuvi."""
from apps.content import richtext as rt


def test_allowed_tags_kept_unknown_escaped():
    out = rt.sanitize_tg('<b>a</b> <i>b</i> <script>x</script> 1 < 2 & 3')
    assert out.startswith("<b>a</b> <i>b</i>")
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "1 &lt; 2 &amp; 3" in out


def test_unclosed_and_misnested_tags_are_fixed():
    assert rt.sanitize_tg("<b><i>x</b>") == "<b><i>x</i></b>"
    assert rt.sanitize_tg("<b>ochiq") == "<b>ochiq</b>"
    assert rt.sanitize_tg("</b>yo'q") == "yo'q"


def test_dangerous_links_rejected_and_entities_kept():
    assert "<a " not in rt.sanitize_tg('<a href="javascript:alert(1)">x</a>')
    assert rt.sanitize_tg('<a href="https://t.me/x?a=1&b=2">l</a>') == '<a href="https://t.me/x?a=1&amp;b=2">l</a>'
    assert rt.sanitize_tg("Q&A &amp; 5>3") == "Q&amp;A &amp; 5&gt;3"


def test_plain_for_instagram_youtube():
    assert rt.for_platform("<b>Salom</b> <a href=\"https://x.uz\">sayt</a>", "instagram") == "Salom sayt (https://x.uz)"
    assert rt.for_platform("<b>a</b>&amp;b", "youtube") == "a&b"


def test_visible_len_ignores_tags():
    assert rt.visible_len("<b>abc</b><a href=\"https://very.long/url\">de</a>") == 5
    assert rt.plain_len("<b>abc</b>", "telegram") == 3


def _texts(rows):
    return [[b["text"] for b in r] for r in rows]


def test_buttons_two_per_row_by_default():
    from apps.web.forms import parse_buttons
    raw = "Murojatlar uchun | https://t.me/a\nTelegram kanal | https://t.me/b\nInstagram | https://instagram.com/c\nYoutube | https://youtube.com/d"
    assert _texts(parse_buttons(raw, 2)) == [["Murojatlar uchun", "Telegram kanal"], ["Instagram", "Youtube"]]
    assert _texts(parse_buttons(raw, 1)) == [["Murojatlar uchun"], ["Telegram kanal"], ["Instagram"], ["Youtube"]]
    assert _texts(parse_buttons(raw, 3)) == [["Murojatlar uchun", "Telegram kanal", "Instagram"], ["Youtube"]]


def test_buttons_explicit_row_and_validation():
    import pytest
    from apps.web.forms import buttons_to_text, parse_buttons
    rows = parse_buttons("A | https://a.uz || B | https://b.uz\nC | https://c.uz", 2)
    assert _texts(rows) == [["A", "B"], ["C"]]
    assert parse_buttons(buttons_to_text(rows), 2) == rows        # tahrirlashda qatorlar saqlanadi
    for bad in ("faqat matn", "A | ftp://x", "A | https://a b"):
        with pytest.raises(ValueError):
            parse_buttons(bad)
