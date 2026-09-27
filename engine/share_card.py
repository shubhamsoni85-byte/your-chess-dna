from io import BytesIO
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


W, H = 1080, 1350
BG = "#0B1020"
PANEL = "#121933"
PANEL_2 = "#182142"
TEXT = "#F6F7FB"
MUTED = "#A9B2CC"
ACCENT = "#7DE2C7"
ACCENT_2 = "#A8B6FF"
LINE = "#263154"


def _font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _round_rect(draw, box, radius=28, fill=PANEL, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _fit_text(draw, text, box_width, max_size, min_size=26, bold=False):
    for size in range(max_size, min_size - 1, -2):
        font = _font(size, bold)
        if draw.textbbox((0, 0), text, font=font)[2] <= box_width:
            return font
    return _font(min_size, bold)


def _wrapped_lines(text, chars=34):
    return wrap(str(text), width=chars, break_long_words=False, break_on_hyphens=False) or [""]


def build_share_card(report, stable_phase, app_url="your-chess-dna.streamlit.app"):
    player = str(report.get("player") or "Chess Player")
    games = int(report.get("games_analyzed") or 0)
    record = report.get("record") or {}
    patterns = [p for p in (report.get("patterns") or []) if p.get("confidence") in ("high", "medium")]
    if not patterns:
        patterns = list(report.get("patterns") or [])

    top = patterns[0] if patterns else {
        "name": "No strong recurring pattern yet",
        "games_observed": 0,
        "positions_observed": 0,
        "thinking_rule": "Analyze more games to build a stronger profile.",
    }
    second = patterns[1] if len(patterns) > 1 else None
    third = patterns[2] if len(patterns) > 2 else None

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # subtle background bands
    d.ellipse((730, -130, 1250, 390), fill="#151E3D")
    d.ellipse((-180, 1030, 360, 1560), fill="#101A34")

    # Header
    d.text((70, 68), "♟  YOUR CHESS DNA", font=_font(28, True), fill=ACCENT)
    d.text((70, 118), "What keeps showing up in your games?", font=_font(42, True), fill=TEXT)
    d.text((70, 180), f"@{player}", font=_fit_text(d, f"@{player}", 760, 48, 30, True), fill=ACCENT_2)

    # summary chips
    chip_y = 245
    chips = [
        f"{games} games",
        f"{record.get('wins',0)}W {record.get('losses',0)}L {record.get('draws',0)}D",
        f"Stable: {stable_phase}",
    ]
    x = 70
    for label in chips:
        font = _font(24, True)
        tw = d.textbbox((0,0), label, font=font)[2]
        _round_rect(d, (x, chip_y, x + tw + 42, chip_y + 54), 27, PANEL_2, LINE, 2)
        d.text((x + 21, chip_y + 13), label, font=font, fill=TEXT)
        x += tw + 58

    # Hero weakness panel
    _round_rect(d, (60, 340, 1020, 760), 34, PANEL, LINE, 2)
    d.text((100, 382), "#1 RECURRING PATTERN", font=_font(24, True), fill=ACCENT)

    name = str(top.get("name", "Recurring Pattern")).upper()
    name_font = _fit_text(d, name, 840, 61, 34, True)
    d.text((100, 433), name, font=name_font, fill=TEXT)

    games_obs = int(top.get("games_observed") or 0)
    pos_obs = int(top.get("positions_observed") or 0)
    big = f"{games_obs} / {games}" if games else str(games_obs)
    d.text((100, 525), big, font=_font(76, True), fill=ACCENT)
    d.text((380, 552), "games showed this signal", font=_font(29, True), fill=MUTED)

    d.line((100, 625, 940, 625), fill=LINE, width=2)
    d.text((100, 650), f"{pos_obs} supporting position{'s' if pos_obs != 1 else ''}", font=_font(28, True), fill=TEXT)

    rule = str(top.get("thinking_rule") or "")
    d.text((100, 697), "TRAINING RULE", font=_font(20, True), fill=ACCENT_2)
    yy = 728
    for line in _wrapped_lines(rule, 52)[:2]:
        d.text((100, yy), line, font=_font(25), fill=MUTED)
        yy += 35

    # Secondary patterns
    d.text((70, 820), "OTHER SIGNALS", font=_font(23, True), fill=MUTED)

    cards = [second, third]
    for i, p in enumerate(cards):
        x0 = 60 + i * 490
        x1 = x0 + 470
        _round_rect(d, (x0, 865, x1, 1060), 26, PANEL_2, LINE, 2)
        if p:
            nm = str(p.get("name") or "")
            d.text((x0 + 30, 895), f"#{i+2}", font=_font(22, True), fill=ACCENT)
            lines = _wrapped_lines(nm, 25)[:2]
            yy2 = 931
            for line in lines:
                d.text((x0 + 30, yy2), line, font=_font(31, True), fill=TEXT)
                yy2 += 38
            d.text(
                (x0 + 30, 1010),
                f"{p.get('games_observed',0)} games · {p.get('positions_observed',0)} positions",
                font=_font(21),
                fill=MUTED,
            )
        else:
            d.text((x0 + 30, 927), "More games =\nstronger profile", font=_font(28, True), fill=TEXT)

    # Footer / CTA
    _round_rect(d, (60, 1125, 1020, 1275), 30, "#0E1630", LINE, 2)
    d.text((95, 1158), "What's your Chess DNA?", font=_font(34, True), fill=TEXT)
    d.text((95, 1205), app_url, font=_font(27, True), fill=ACCENT)
    d.text((815, 1180), "FREE", font=_font(30, True), fill=ACCENT_2)

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
