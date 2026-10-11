"""Targetolog uchun topshiriq (brief): bitta PDF sahifa. Reklamani targetolog o'zi yoqadi."""
from __future__ import annotations

import io

from apps.core.settings_store import get_setting

from .guides import guide_for
from .proposals import OBJ_LABEL, PLAT_AD

VERDICT_UZ = {"advertise": "Reklama qilish tavsiya etiladi", "improve_first": "Avval kontentni yaxshilash tavsiya etiladi", "wait": "Hozircha ma'lumot yetarli emas"}
CONF_UZ = {"low": "past", "medium": "o'rtacha", "high": "yuqori"}


def norm(t) -> str:
    return str(t or "").replace("ʻ", "'").replace("ʼ", "'").replace("’", "'").replace("‘", "'")


def build_brief_pdf(p) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from apps.reports.generator import FONT_DIR
    try:
        pdfmetrics.registerFont(TTFont("DV", str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DV-B", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV", boldItalic="DV-B")
        f, fb = "DV", "DV-B"
    except Exception:  # noqa: BLE001
        f, fb = "Helvetica", "Helvetica-Bold"
    brand = colors.HexColor(get_setting("reports.brand_color", "#E11D2E"))
    ink, muted, line, soft = colors.HexColor("#0f172a"), colors.HexColor("#64748b"), colors.HexColor("#e2e8f0"), colors.HexColor("#f8fafc")
    P = ParagraphStyle("p", fontName=f, fontSize=9.5, leading=14, textColor=ink)
    PS = ParagraphStyle("ps", fontName=f, fontSize=8.5, leading=12, textColor=muted)
    H1 = ParagraphStyle("h1", fontName=fb, fontSize=18, leading=22, textColor=ink, spaceAfter=2)
    H2 = ParagraphStyle("h2", fontName=fb, fontSize=12.5, leading=16, textColor=brand, spaceBefore=12, spaceAfter=4)
    r, ev = p.result or {}, p.evidence or {}
    buf = io.BytesIO()
    W, _ = A4
    LM = 16 * mm
    CW = W - 2 * LM

    def bullets(items):
        items = [norm(x) for x in items if x]
        if not items:
            return Paragraph("—", P)
        return ListFlowable([ListItem(Paragraph(x, P), leftIndent=10) for x in items], bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8)

    def on_page(c, doc):
        c.saveState()
        c.setFillColor(brand)
        c.rect(0, A4[1] - 6 * mm, W, 6 * mm, stroke=0, fill=1)
        c.setFillColor(muted)
        c.setFont(f, 7.5)
        c.drawString(LM, 9 * mm, norm(f"{get_setting('general.system_name', 'SMM Platforma')} · targetolog uchun topshiriq · taklif, reklama bu tizimda yoqilmaydi"))
        c.drawRightString(W - LM, 9 * mm, f"{doc.page}-bet")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=LM, rightMargin=LM, topMargin=16 * mm, bottomMargin=18 * mm, title=norm(f"{p.business.name} reklama topshirig'i"))
    st = []
    st += [Paragraph(norm(f"Reklama topshirig'i: {p.business.name}"), H1),
           Paragraph(norm(f"{PLAT_AD.get(p.platform, p.platform)} · {p.account.name} · maqsad: {OBJ_LABEL.get(p.objective, p.objective)} · {p.created_at:%d.%m.%Y}"), PS), Spacer(1, 4 * mm)]
    box = Table([[Paragraph(f"<b>{norm(VERDICT_UZ.get(r.get('verdict'), ''))}</b><br/>{norm(r.get('summary', ''))}", P)]], colWidths=[CW])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), soft), ("BOX", (0, 0), (-1, -1), .6, line), ("LINEBEFORE", (0, 0), (0, -1), 3, brand),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    st += [box, Paragraph(norm(f"Ishonch darajasi: {CONF_UZ.get(p.confidence, p.confidence)}" + (" · " + "; ".join(ev.get("confidence_reasons", [])) if ev.get("confidence_reasons") else "")), PS)]
    pg = r.get("platform_goal") or {}
    st += [Paragraph("Reklama maqsadi (platformada)", H2), Paragraph(norm(f"<b>{pg.get('name', '')}</b> — {pg.get('why', '')}"), P)]
    st.append(Paragraph("Reklama qilinadigan kontent", H2))
    for pk in r.get("picks", []):
        rows = [[Paragraph(norm(f"<b>{pk['rank']}. {pk['title']}</b>"), P)],
                [Paragraph(norm(f"Ball: {pk['score']} · havola: {pk.get('url') or '—'}"), PS)],
                [Paragraph("Nega: " + norm("; ".join(pk.get("why", []))), P)]]
        if pk.get("directions"):
            rows.append([Paragraph("Xabar yo'nalishlari: " + norm("; ".join(pk["directions"])), P)])
        if pk.get("improve"):
            rows.append([Paragraph("Reklamadan oldin yaxshilash: " + norm("; ".join(pk["improve"])), P)])
        t = Table(rows, colWidths=[CW])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .6, line), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        st += [KeepTogether([t]), Spacer(1, 2 * mm)]
    if not r.get("picks"):
        st.append(Paragraph("Nomzod yo'q.", P))
    a = r.get("audience") or {}
    st += [Paragraph("Auditoriya", H2), Paragraph(norm(a.get("summary", "")), P),
           Paragraph(norm(f"Hudud: {', '.join(a.get('regions', []))} · Yosh: {a.get('age', '—')}"), P)]
    if a.get("interests"):
        st.append(Paragraph(norm("Qiziqishlar: " + ", ".join(a["interests"])), P))
    if a.get("channels_topics"):
        st.append(Paragraph(norm("Kanal/mavzular: " + ", ".join(a["channels_topics"])), P))
    if a.get("note"):
        st.append(Paragraph(norm(a["note"]), PS))
    tp = r.get("test_plan") or {}
    st += [Paragraph("Sinov rejasi", H2), Paragraph(norm(f"Muddat: {tp.get('duration_days', '—')} kun"), P), Paragraph("Variantlar:", P), bullets(tp.get("variants", [])),
           Paragraph("Muvaffaqiyat belgilari:", P), bullets(tp.get("success_signals", [])), Paragraph("To'xtatish belgilari:", P), bullets(tp.get("stop_signals", []))]
    st += [Paragraph("Kreativ bo'yicha eslatmalar", H2), bullets(r.get("creative_notes", [])), Paragraph("Nima qilmaslik kerak", H2), bullets(r.get("avoid", []))]
    g = guide_for(p.platform, p.objective)
    st.append(Paragraph(norm(g["title"]), H2))
    st.append(ListFlowable([ListItem(Paragraph(norm(f"<b>{t}.</b> {d}"), P), leftIndent=12) for t, d in g["steps"]], bulletType="1", leftIndent=14))
    st.append(Paragraph(norm(f"{g['disclaimer']} (qo'llanma {g['checked']} holatiga ko'ra)"), PS))
    if p.note:
        st += [Paragraph("Izoh", H2), Paragraph(norm(p.note), P)]
    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
