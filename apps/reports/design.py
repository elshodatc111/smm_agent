"""Mijoz ko'rinishidagi chiroyli hisobot: PDF (ReportLab) va bir xil dizayndagi HTML sahifa (SVG grafiklar bilan)."""
from __future__ import annotations

import io
import os
from html import escape as esc

from apps.core.settings_store import get_setting
from apps.core.utils import fmt_num

PLAT_COLOR = {"telegram": "#229ED9", "instagram": "#E1306C", "youtube": "#FF0000"}
TYPE_UZ = {"text": "Matn", "image": "Rasm", "video": "Video", "album": "Albom", "reel": "Reels", "short": "Shorts", "story": "Stories", "carousel": "Karusel", "post": "Post"}


def norm(t) -> str:
    return str(t or "").replace("ʻ", "'").replace("ʼ", "'").replace("’", "'").replace("‘", "'")


def pct(v) -> str:
    return "" if v is None else f"{v:+.0f}%"


def brand() -> str:
    return get_setting("reports.brand_color", "#E11D2E")


def kpi_cards(data: dict) -> list[dict]:
    k, d = data["kpi"], data["delta"]
    er = f"{(k.get('er') or 0) * 100:.1f}%"
    return [
        {"label": "Obunachilar", "value": fmt_num(k["followers"]), "sub": f"{k['followers_delta']:+d} davr ichida", "delta": k.get("followers_growth_pct")},
        {"label": "Ko'rishlar", "value": fmt_num(k["views"]), "sub": "jami ko'rishlar", "delta": d.get("views")},
        {"label": "Qamrov", "value": fmt_num(k["reach"]), "sub": "noyob foydalanuvchilar", "delta": d.get("reach")},
        {"label": "Postlar", "value": str(k["posts"]), "sub": f"{(data.get('stories') or {}).get('count', 0)} ta stories", "delta": d.get("posts")},
        {"label": "Faollik (ER)", "value": er, "sub": f"{fmt_num(k['likes'])} layk · {fmt_num(k['comments'])} izoh", "delta": d.get("er")},
    ]


# ------------------------------------------------------------------ SVG (HTML sahifa uchun)
def svg_line(vals: list[float], labels: list[str], color: str, w: int = 640, h: int = 180) -> str:
    vals = [v or 0 for v in vals]
    if len(vals) < 2:
        return '<div class="muted">Grafik uchun ma\'lumot yetarli emas.</div>'
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pad, W, H = 28, w, h
    pts = [(pad + i * (W - 2 * pad) / (len(vals) - 1), H - 24 - (v - lo) / span * (H - 48)) for i, v in enumerate(vals)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{H - 24} " + path + f" {pts[-1][0]:.1f},{H - 24}"
    lab = "".join(f'<text x="{pts[i][0]:.0f}" y="{H - 6}" text-anchor="middle" font-size="10" fill="#94a3b8">{esc(labels[i])}</text>' for i in sorted({0, len(vals) // 2, len(vals) - 1}))
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img"><defs><linearGradient id="g{abs(hash(color)) % 999}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity=".25"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="{area}" fill="url(#g{abs(hash(color)) % 999})"/><polyline points="{path}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<text x="{pad}" y="14" font-size="11" fill="#64748b">{fmt_num(hi)}</text><text x="{pad}" y="{H - 28}" font-size="11" fill="#64748b">{fmt_num(lo)}</text>{lab}</svg>')


def svg_bars(vals: list[float], labels: list[str], color: str, w: int = 640, h: int = 150) -> str:
    vals = [v or 0 for v in vals]
    if not vals or not any(vals):
        return '<div class="muted">Bu davrda ma\'lumot yo\'q.</div>'
    hi = max(vals) or 1
    n = len(vals)
    bw = max(2, (w - 40) / n * 0.7)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    for i, v in enumerate(vals):
        x = 20 + i * (w - 40) / n
        bh = v / hi * (h - 36)
        out.append(f'<rect x="{x:.1f}" y="{h - 22 - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{color}"/>')
    for i in sorted({0, n // 2, n - 1}):
        out.append(f'<text x="{20 + i * (w - 40) / n + bw / 2:.0f}" y="{h - 6}" text-anchor="middle" font-size="10" fill="#94a3b8">{esc(labels[i])}</text>')
    out.append(f'<text x="20" y="12" font-size="11" fill="#64748b">max {fmt_num(hi)}</text></svg>')
    return "".join(out)


def html_context(report) -> dict:
    d = report.data or {}
    daily = d.get("daily") or []
    labels = [x["day"][5:].replace("-", ".") for x in daily]
    col = brand()
    s = d.get("summary") or {}
    d = {**d, "top": [{**p, "type_uz": TYPE_UZ.get(p["type"], p["type"]), "er_pct": f"{(p.get('er') or 0) * 100:.1f}%", "views": fmt_num(p.get("views"))} for p in d.get("top", [])],
         "publications": [{**p, "type_uz": TYPE_UZ.get(p["type"], p["type"])} for p in d.get("publications", [])],
         "per_platform": [{**x, "kpi": {**x["kpi"], "er_pct": f"{(x['kpi'].get('er') or 0) * 100:.1f}%", "followers": fmt_num(x["kpi"]["followers"]), "views": fmt_num(x["kpi"]["views"]), "likes": fmt_num(x["kpi"]["likes"]),
                                         "followers_delta": f"{x['kpi']['followers_delta']:+d}"}} for x in d.get("per_platform", [])]}
    return {"report": report, "business": report.business, "brand": col, "system_name": get_setting("general.system_name", "SMM Platforma"), "d": d,
            "cards": kpi_cards(d) if d.get("kpi") else [], "summary": s.get("summary") or report.summary_text, "recs": s.get("recommendations") or [],
            "chart_followers": svg_line([x["followers"] or 0 for x in daily], labels, col), "chart_views": svg_bars([x["views"] for x in daily], labels, col),
            "plat_color": PLAT_COLOR, "type_uz": TYPE_UZ, "has_daily": bool(daily)}


# ------------------------------------------------------------------ PDF
def build_pdf(report, data: dict, summary: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import BaseDocTemplate, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle
    from .generator import FONT_DIR
    try:
        pdfmetrics.registerFont(TTFont("DV", str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DV-B", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV", boldItalic="DV-B")
        f, fb = "DV", "DV-B"
    except Exception:  # noqa: BLE001
        f, fb = "Helvetica", "Helvetica-Bold"
    brand_c = colors.HexColor(brand())
    ink, muted, line, soft = colors.HexColor("#0f172a"), colors.HexColor("#64748b"), colors.HexColor("#e2e8f0"), colors.HexColor("#f8fafc")
    ok, bad = colors.HexColor("#16a34a"), colors.HexColor("#dc2626")
    sys_name = norm(get_setting("general.system_name", "SMM Platforma"))
    W, Hh = A4
    LM = 16 * mm
    CW = W - 2 * LM
    P = ParagraphStyle("p", fontName=f, fontSize=9.5, leading=14, textColor=ink)
    PS = ParagraphStyle("ps", fontName=f, fontSize=8, leading=11, textColor=muted)
    H2 = ParagraphStyle("h2", fontName=fb, fontSize=13, leading=17, textColor=ink, spaceBefore=14, spaceAfter=6)
    buf = io.BytesIO()

    def page_deco(c, doc):
        c.saveState()
        if doc.page == 1:
            c.setFillColor(brand_c)
            c.rect(0, Hh - 46 * mm, W, 46 * mm, stroke=0, fill=1)
            c.setFillColor(colors.Color(1, 1, 1, alpha=0.12))
            c.circle(W - 20 * mm, Hh - 12 * mm, 38 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(fb, 20)
            c.drawString(LM, Hh - 22 * mm, norm(report.business.name)[:46])
            c.setFont(f, 10.5)
            c.drawString(LM, Hh - 30 * mm, norm(f"{report.get_kind_display()} hisobot  ·  {report.period_start:%d.%m.%Y} – {report.period_end:%d.%m.%Y}"))
            c.setFont(f, 8.5)
            c.drawString(LM, Hh - 38 * mm, sys_name)
            lp = report.business.logo.path if (report.with_client_logo and report.business.logo) else get_setting("reports.logo", "")
            if lp and os.path.exists(str(lp)):
                try:
                    c.drawImage(str(lp), W - LM - 30 * mm, Hh - 36 * mm, width=30 * mm, height=22 * mm, preserveAspectRatio=True, mask="auto")
                except Exception:  # noqa: BLE001
                    pass
        else:
            c.setFillColor(brand_c)
            c.rect(0, Hh - 7 * mm, W, 7 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(f, 8)
            c.drawString(LM, Hh - 5 * mm, norm(f"{report.business.name} · {report.period_start:%d.%m.%Y} – {report.period_end:%d.%m.%Y}"))
        c.setFillColor(muted)
        c.setFont(f, 7.5)
        c.drawString(LM, 9 * mm, norm(f"{sys_name} · avtomatik tayyorlangan hisobot"))
        c.drawRightString(W - LM, 9 * mm, f"{doc.page}-bet")
        c.setStrokeColor(line)
        c.line(LM, 13 * mm, W - LM, 13 * mm)
        c.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=LM, rightMargin=LM, topMargin=16 * mm, bottomMargin=18 * mm, title=norm(f"{report.business.name} hisobot"), author=sys_name)
    first = Frame(LM, 18 * mm, CW, Hh - 18 * mm - 52 * mm, id="f1", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(LM, 18 * mm, CW, Hh - 18 * mm - 16 * mm, id="f2", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="first", frames=[first], onPage=page_deco, autoNextPageTemplate="rest"), PageTemplate(id="rest", frames=[later], onPage=page_deco)])

    story = []
    # KPI kartalar (3x2)
    cards = kpi_cards(data)

    def card(c):
        dl = c["delta"]
        dcol = ok if (dl or 0) >= 0 else bad
        dtxt = "" if dl is None else f'<font color="{"#16a34a" if dl >= 0 else "#dc2626"}">{"▲" if dl >= 0 else "▼"} {abs(dl):.0f}%</font>'
        inner = [Paragraph(norm(c["label"]), ParagraphStyle("l", fontName=f, fontSize=8, textColor=muted)),
                 Paragraph(f'<font size="18" name="{fb}">{norm(c["value"])}</font>', ParagraphStyle("v", fontName=fb, fontSize=18, leading=22, textColor=ink)),
                 Paragraph(norm(c["sub"]) + ("  " + dtxt if dtxt else ""), ParagraphStyle("s", fontName=f, fontSize=7.5, leading=10, textColor=muted))]
        t = Table([[inner]], colWidths=[CW / 3 - 4 * mm])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, line), ("BACKGROUND", (0, 0), (-1, -1), soft), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LINEBEFORE", (0, 0), (0, -1), 3, brand_c)]))
        return t
    grid = Table([[card(cards[0]), card(cards[1]), card(cards[2])], [card(cards[3]), card(cards[4]), ""]], colWidths=[CW / 3] * 3, rowHeights=None)
    grid.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [Spacer(1, 2 * mm), grid]

    # xulosa
    box = Table([[Paragraph("<b>Qisqacha xulosa</b><br/>" + norm(summary["summary"]).replace("\n", "<br/>"), P)]], colWidths=[CW])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7f7") if True else soft), ("BOX", (0, 0), (-1, -1), 0.6, line), ("LINEBEFORE", (0, 0), (0, -1), 3, brand_c),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [box]

    daily = data.get("daily") or []
    series = data.get("series") or []

    def line_chart(vals, color):
        dr = Drawing(CW, 52 * mm)
        lp = LinePlot()
        lp.x, lp.y, lp.width, lp.height = 30, 16, CW - 40, 52 * mm - 28
        lp.data = [[(i, v or 0) for i, v in enumerate(vals)]]
        lp.lines[0].strokeColor = colors.HexColor(color)
        lp.lines[0].strokeWidth = 2
        lp.xValueAxis.visible = False
        lp.yValueAxis.labels.fontName, lp.yValueAxis.labels.fontSize = f, 7
        lp.yValueAxis.strokeColor = line
        lp.yValueAxis.gridStart, lp.yValueAxis.gridEnd = lp.x, lp.x + lp.width
        lp.yValueAxis.visibleGrid = True
        lp.yValueAxis.gridStrokeColor = colors.HexColor("#eef2f7")
        dr.add(lp)
        return dr

    def bar_chart(vals, color):
        dr = Drawing(CW, 42 * mm)
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 30, 12, CW - 40, 42 * mm - 22
        bc.data = [[v or 0 for v in vals]]
        bc.bars[0].fillColor = colors.HexColor(color)
        bc.bars[0].strokeColor = None
        bc.barWidth = 3
        bc.categoryAxis.visible = False
        bc.valueAxis.labels.fontName, bc.valueAxis.labels.fontSize = f, 7
        bc.valueAxis.strokeColor = line
        dr.add(bc)
        return dr

    fvals = [x["followers"] for x in daily if x.get("followers") is not None]
    if len(fvals) < 2:
        fvals = [p["followers"] for p in series]
    if len(fvals) >= 2:
        story.append(KeepTogether([Paragraph("Obunachilar dinamikasi", H2), line_chart(fvals, brand())]))
    if daily and any(x["views"] for x in daily):
        story.append(KeepTogether([Paragraph("Kunlik ko'rishlar", H2), bar_chart([x["views"] for x in daily], "#6366f1")]))

    # platformalar
    per = data.get("per_platform") or []
    if per:
        rows = [["Platforma", "Obunachi", "O'sish", "Postlar", "Ko'rish", "Layk", "ER"]]
        for x in per:
            k = x["kpi"]
            rows.append([x["name"], fmt_num(k["followers"]), f"{k['followers_delta']:+d}", str(k["posts"]), fmt_num(k["views"]), fmt_num(k["likes"]), f"{(k['er'] or 0) * 100:.1f}%"])
        t = Table([[norm(c) for c in r] for r in rows], colWidths=[CW * 0.22, CW * 0.14, CW * 0.12, CW * 0.12, CW * 0.16, CW * 0.12, CW * 0.12])
        t.setStyle(_tbl_style(f, fb, brand_c, line, soft))
        story += [Paragraph("Platformalar bo'yicha", H2), t]

    # top postlar
    if data.get("top"):
        rows = [["Post", "Tur", "Platforma", "Ko'rish", "ER"]] + [[Paragraph(norm(p["text"]) or "—", PS), TYPE_UZ.get(p["type"], p["type"]), norm(p["platform"]).title(), fmt_num(p["views"]), f"{(p['er'] or 0) * 100:.1f}%"] for p in data["top"]]
        t = Table(rows, colWidths=[CW * 0.44, CW * 0.12, CW * 0.16, CW * 0.14, CW * 0.12])
        t.setStyle(_tbl_style(f, fb, brand_c, line, soft))
        story += [Paragraph("Eng yaxshi postlar", H2), t]

    # nashrlar
    pubs = data.get("publications") or []
    if pubs:
        rows = [["Sana", "Platforma", "Tur", "Mazmun"]] + [[x["when"], norm(x["platform"]).title(), TYPE_UZ.get(x["type"], x["type"]), Paragraph(norm(x["text"]) or "—", PS)] for x in pubs[:25]]
        t = Table(rows, colWidths=[CW * 0.16, CW * 0.16, CW * 0.12, CW * 0.56], repeatRows=1)
        t.setStyle(_tbl_style(f, fb, brand_c, line, soft))
        story += [Paragraph(f"Davrda chiqqan nashrlar ({len(pubs)} ta)", H2), t]

    st = data.get("stories") or {}
    if st.get("count"):
        story += [Paragraph("Stories", H2), Paragraph(norm(f"Davrda {st['count']} ta stories joylandi, jami {fmt_num(st['views'])} ko'rish oldi."), P)]

    if data.get("competitors"):
        rows = [["Raqobatchi", "Tarmoq", "Obunachi", "O'sish"]] + [[norm(c["name"]), norm(c["platform"]).title(), fmt_num(c["followers"]), f"{c['growth']:+d}"] for c in data["competitors"]]
        t = Table(rows, colWidths=[CW * 0.4, CW * 0.2, CW * 0.2, CW * 0.2])
        t.setStyle(_tbl_style(f, fb, brand_c, line, soft))
        story += [Paragraph("Raqobatchilar bilan solishtirish", H2), t]

    recs = summary.get("recommendations") or []
    if recs:
        story.append(Paragraph("Keyingi davr uchun tavsiyalar", H2))
        for i, r in enumerate(recs, 1):
            row = Table([[Paragraph(f'<font color="white"><b>{i}</b></font>', ParagraphStyle("n", fontName=fb, fontSize=10, alignment=1)), Paragraph(norm(r), P)]], colWidths=[8 * mm, CW - 8 * mm])
            row.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), brand_c), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 0.5, line), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            story += [row, Spacer(1, 2 * mm)]
    doc.build(story)
    return buf.getvalue()


def _tbl_style(f, fb, brand_c, line, soft):
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle
    return TableStyle([("FONTNAME", (0, 0), (-1, -1), f), ("FONTNAME", (0, 0), (-1, 0), fb), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("BACKGROUND", (0, 0), (-1, 0), brand_c),
                       ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]), ("LINEBELOW", (0, 0), (-1, -1), 0.25, line),
                       ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)])
