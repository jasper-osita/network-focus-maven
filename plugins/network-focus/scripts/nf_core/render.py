"""Turn a validated brief.json into the one-page PDF (and a Markdown copy).
The "Check before the meeting" box is filled from warnings.json by code, so the model can't drop a warning."""
import io
import unicodedata
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from .snapshot import BANNER_CODES, questions_for

FONT_SIZES = (10, 9.5, 9, 8.5, 8)
_ASCII = {"→": "->", "←": "<-", "≥": ">=", "≤": "<=", "✓": "v", "✅": "v", "❌": "x", "⚠": "!", "•": "-",
          "≈": "~", "×": "x"}


def pdf_safe(text: str) -> str:
    """Built-in PDF fonts only cover Western European characters; never let a name crash the brief."""
    out = []
    for ch in str(text):
        ch = _ASCII.get(ch, ch)
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", ch).encode("cp1252", "ignore").decode("cp1252")
            out.append(base or "?")
    return "".join(out)


# Embeddable fallback fonts, tried in order for characters Helvetica can't draw. Loaded only when needed.
WIDE_FONTS = ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Songti.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
              "C:/Windows/Fonts/arial.ttf")
_LOADED: list[tuple[str, set]] = []
_STATE = {"next": 0, "cjk": None, "cjk_tried": False}


def _font_with_glyph(ch: str) -> str | None:
    """Name of a registered font that can draw `ch`, loading more fallback fonts only as needed."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    code = ord(ch)
    for name, glyphs in _LOADED:
        if code in glyphs:
            return name
    while _STATE["next"] < len(WIDE_FONTS):
        path = WIDE_FONTS[_STATE["next"]]
        _STATE["next"] += 1
        if not Path(path).exists():
            continue
        try:
            name = f"NFWide{len(_LOADED)}"
            font = TTFont(name, path, subfontIndex=0) if path.endswith(".ttc") else TTFont(name, path)
            pdfmetrics.registerFont(font)
            _LOADED.append((name, set(font.face.charToGlyph)))
        except Exception:
            continue
        if code in _LOADED[-1][1]:
            return name
    if not _STATE["cjk_tried"]:  # last resort: built-in CJK font (not embedded; most PDF readers can show it)
        _STATE["cjk_tried"] = True
        try:
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            _STATE["cjk"] = "STSong-Light"
        except Exception:
            pass
    return _STATE["cjk"] if _STATE["cjk"] and _gb_ok(ch) else None


def pdf_markup(text: str) -> str:
    """Escape text for a ReportLab Paragraph, switching font for runs Helvetica can't draw (e.g. 李伟, Łukasz)."""
    runs: list[tuple[str | None, str]] = []
    for ch in str(text):
        ch = _ASCII.get(ch, ch)
        font = None
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            font = _font_with_glyph(ch)
            if font is None:
                ch = pdf_safe(ch)
        if runs and runs[-1][0] == font:
            runs[-1] = (font, runs[-1][1] + ch)
        else:
            runs.append((font, ch))
    return "".join(escape(t) if f is None else f'<font name="{f}">{escape(t)}</font>' for f, t in runs)


def _gb_ok(ch: str) -> bool:
    try:
        ch.encode("gb2312")
        return True
    except UnicodeEncodeError:
        return False


def _fmt(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def _ctx(brief: dict, roster: dict, warnings: dict) -> dict:
    rows = {c["row_id"]: c for c in roster["contacts"]}
    goals = {g["id"]: g["title"] for g in roster["goals"]}
    ws = warnings.get("warnings", [])
    banner = [w["message"] for w in ws if w["code"] in BANNER_CODES]
    checks = questions_for(brief, roster, warnings)  # same list the dashboard shows as "questions for you"

    def who(item):
        r = rows[item["row_id"]]
        return ", ".join(x for x in (r["role"], r["company"]) if x)

    picked = {x["row_id"] for sec in ("focus", "dormant", "coming_up") for x in brief.get(sec, [])}
    soon = [w for w in ws if w["code"] == "NEAR_DORMANT" and not set(w.get("rows", [])) & picked]
    return {"rows": rows, "goals": goals, "banner": banner, "checks": checks, "who": who,
            "soon": [w["message"] for w in soon],
            "info": [w["message"] for w in ws if w["severity"] == "info" and w not in soon],
            "src": roster["source"]}


def render_markdown(brief: dict, roster: dict, warnings: dict) -> str:
    c = _ctx(brief, roster, warnings)
    src = c["src"]
    lines = [f"# NETWORK FOCUS · Week of {_fmt(brief['week_of'])}",
             f"Data as of: {_fmt(src['as_of'])} (file date) · {src['file_name']}", ""]
    for b in c["banner"]:
        lines += [f"> **Data warning:** {b}", ""]
    lines += [f"## THIS WEEK ({len(brief['focus'])})", ""]
    for i, f in enumerate(brief["focus"], 1):
        goals = " + ".join(c["goals"].get(g, f"Goal {g}") for g in f["goals"])
        low = " · low confidence" if f["confidence"] == "low" else ""
        lines += [f"### {i}. {f['name']} · {c['who'](f)} · {goals}{low}",
                  f"- **Why:** {f['why']}", f"- **Move:** {f['move']}", f"- **At risk:** {f['risk']}"]
        if f.get("message"):
            lines.append(f"- **Message:** {f['message']}")
        lines.append("")
    lines += [f"## DORMANT BUT HIGH-LEVERAGE ({len(brief['dormant'])})", ""]
    for d in brief["dormant"]:
        lines.append(f"- **{d['name']}** · {c['who'](d)} · {d['days_since_contact']} days. {d['why']} "
                     f"**Move:** {d['move']}" + (f" **Message:** {d['message']}" if d.get("message") else ""))
    lines.append("")
    if brief.get("coming_up") or c["soon"]:
        lines += ["## COMING UP", ""] + [f"- **{x['name']}**: {x['note']}" for x in brief["coming_up"]]
        lines += [f"- Goes quiet soon: {m}" for m in c["soon"]] + [""]
    lines += ["## CHECK BEFORE THE MEETING", ""] + [f"- {m}" for m in c["checks"] or ["Nothing to flag."]] + [""]
    if c["info"]:
        lines += ["## Also noted", ""] + [f"- {m}" for m in c["info"]] + [""]
    return "\n".join(lines)


def _story(brief, c, size, styles):
    from reportlab.platypus import Paragraph, Spacer
    s = styles(size)
    p = lambda text, st: Paragraph(pdf_markup(str(text).replace("**", "")), s[st])
    m = pdf_markup
    src = c["src"]
    story = [p(f"NETWORK FOCUS · Week of {_fmt(brief['week_of'])}", "title"),
             p(f"Data as of: {_fmt(src['as_of'])} (file date) · {src['file_name']}", "meta")]
    for b in c["banner"]:
        story.append(p(f"Data warning: {b}", "banner"))
    story.append(p(f"THIS WEEK ({len(brief['focus'])})", "h"))
    for i, f in enumerate(brief["focus"], 1):
        goals = " + ".join(c["goals"].get(g, f"Goal {g}") for g in f["goals"])
        low = " · low confidence" if f["confidence"] == "low" else ""
        story.append(p(f"{i}. {f['name']} · {c['who'](f)} · {goals}{low}", "name"))
        for label, key in (("Why", "why"), ("Move", "move"), ("At risk", "risk")):
            story.append(Paragraph(f"<b>{label}:</b> {m(f[key])}", s["body"]))
    story.append(p(f"DORMANT BUT HIGH-LEVERAGE ({len(brief['dormant'])})", "h"))
    for d in brief["dormant"]:
        story.append(Paragraph(f"<b>{m(d['name'])}</b> · {m(c['who'](d))} · "
                               f"{d['days_since_contact']} days. {m(d['why'])} "
                               f"<b>Move:</b> {m(d['move'])}", s["bullet"]))
    if brief.get("coming_up") or c["soon"]:
        story.append(p("COMING UP", "h"))
        for x in brief["coming_up"]:
            story.append(Paragraph(f"<b>{m(x['name'])}</b>: {m(x['note'])}", s["bullet"]))
        for msg in c["soon"]:
            story.append(Paragraph(f"Goes quiet soon: {m(msg)}", s["bullet"]))
    story.append(p("CHECK BEFORE THE MEETING", "h"))
    for m in c["checks"] or ["Nothing to flag."]:
        story.append(p(f"- {m}", "check"))
    story.append(Spacer(1, 2))
    return story


def _styles(size):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    ink, navy, gray, beige, gold = (HexColor(x) for x in ("#2B2B2B", "#1F2A44", "#6B6B6B", "#F3EBDD", "#B08D57"))
    lead = size * 1.25
    base = dict(fontName="Helvetica", fontSize=size, leading=lead, textColor=ink)
    return {
        "title": ParagraphStyle("title", **{**base, "fontName": "Helvetica-Bold", "fontSize": size + 5,
                                            "leading": (size + 5) * 1.2, "textColor": navy}),
        "meta": ParagraphStyle("meta", **{**base, "textColor": gray, "spaceAfter": size * 0.6}),
        "banner": ParagraphStyle("banner", **{**base, "backColor": beige, "borderPadding": 4,
                                              "spaceBefore": 2, "spaceAfter": size * 0.8}),
        "h": ParagraphStyle("h", **{**base, "fontName": "Helvetica-Bold", "fontSize": size + 1.5, "textColor": gold,
                                    "spaceBefore": size * 0.7, "spaceAfter": size * 0.3}),
        "name": ParagraphStyle("name", **{**base, "fontName": "Helvetica-Bold", "textColor": navy,
                                          "spaceBefore": size * 0.35}),
        "body": ParagraphStyle("body", **{**base, "leftIndent": 10}),
        "bullet": ParagraphStyle("bullet", **{**base, "leftIndent": 10, "spaceAfter": 2}),
        "check": ParagraphStyle("check", **{**base, "leftIndent": 10}),
    }


def render_pdf(brief: dict, roster: dict, warnings: dict, out: Path) -> int:
    """Write the PDF at the largest font size that fits one page. Returns the page count used."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate
    c = _ctx(brief, roster, warnings)
    for size in FONT_SIZES:
        buf, pages = io.BytesIO(), [0]
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                                topMargin=0.55 * inch, bottomMargin=0.55 * inch, title="Network Focus brief")
        count = lambda canvas, d: pages.__setitem__(0, pages[0] + 1)
        doc.build(_story(brief, c, size, _styles), onFirstPage=count, onLaterPages=count)
        if pages[0] == 1:
            break
    Path(out).write_bytes(buf.getvalue())
    return pages[0]
