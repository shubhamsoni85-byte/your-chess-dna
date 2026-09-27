from io import BytesIO
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


W, H = 1080, 1350

BG = "#07101F"
PANEL = "#101A35"
PANEL_ALT = "#152142"
TEXT = "#F7FAFF"
MUTED = "#A9B4D0"
ACCENT = "#57E7D6"
ACCENT_2 = "#8EA4FF"
LINE = "#28406F"
SOFT = "#0C1730"


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


def _fit(draw, text, max_width, max_size, min_size=26, bold=False):
    for size in range(max_size, min_size - 1, -2):
        f = _font(size, bold)
        box = draw.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_width:
            return f
    return _font(min_size, bold)


def _rr(draw, box, radius=28, fill=PANEL, outline=LINE, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _pill(draw, x, y, label, font, fill=PANEL_ALT, text_fill=TEXT):
    tw = draw.textbbox((0, 0), label, font=font)[2]
    box = (x, y, x + tw + 38, y + 52)
    _rr(draw, box, radius=26, fill=fill)
    draw.text((x + 19, y + 12), label, font=font, fill=text_fill)
    return box[2]


def _wrap_lines(text, width):
    return wrap(str(text), width=width, break_long_words=False, break_on_hyphens=False) or [""]


def _draw_knight_mark(draw, cx, cy, scale=1.0):
    # Simple abstract knight/strategy motif built from vector primitives.
    r = int(54 * scale)
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=ACCENT, width=max(2, int(3*scale)))
    draw.arc((cx-r//2, cy-r//2, cx+r//2, cy+r//2), start=205, end=30, fill=ACCENT, width=max(3, int(5*scale)))
    draw.line((cx-16*scale, cy+15*scale, cx+12*scale, cy-20*scale), fill=ACCENT, width=max(3, int(5*scale)))
    draw.line((cx+12*scale, cy-20*scale, cx+27*scale, cy+4*scale), fill=ACCENT, width=max(3, int(5*scale)))


def build_share_card(report, stable_phase, app_url="your-chess-dna.streamlit.app"):
    player = str(report.get("player") or "Chess Player")
    games = int(report.get("games_analyzed") or 0)
    record = report.get("record") or {}

    patterns = [
        p for p in (report.get("patterns") or [])
        if p.get("confidence") in ("high", "medium")
    ]
    if not patterns:
        patterns = list(report.get("patterns") or [])

    fallback = {
        "name": "No strong recurring pattern yet",
        "games_observed": 0,
        "positions_observed": 0,
        "thinking_rule": "Analyze more games to build a stronger profile.",
    }
    top = patterns[0] if patterns else fallback
    second = patterns[1] if len(patterns) > 1 else None
    third = patterns[2] if len(patterns) > 2 else None

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Background depth
    d.ellipse((730, -120, 1240, 390), fill="#132344")
    d.ellipse((-210, 1030, 360, 1570), fill="#0E1B37")
    d.polygon([(820,0),(1080,0),(1080,370),(930,430),(790,270)], fill="#0A1830")

    # Brand
    d.text((70, 52), "YOUR CHESS DNA", font=_font(27, True), fill=ACCENT)
    d.line((70, 91, 210, 91), fill=ACCENT, width=3)

    # Hook
    d.text((70, 118), "THE MISTAKE YOU", font=_font(58, True), fill=TEXT)
    d.text((70, 180), "KEEP REPEATING", font=_font(64, True), fill=ACCENT)
    d.text((70, 252), f"@{player}", font=_fit(d, f"@{player}", 700, 34, 24, True), fill=ACCENT_2)

    # Top summary pills
    pill_font = _font(22, True)
    x = 70
    y = 306
    x = _pill(d, x, y, f"{games} games", pill_font) + 16
    x = _pill(d, x, y, f"{record.get('wins',0)}W {record.get('losses',0)}L {record.get('draws',0)}D", pill_font) + 16
    _pill(d, x, y, f"Stable: {stable_phase}", pill_font)

    # Hero card
    _rr(d, (48, 390, 1032, 916), radius=34, fill=PANEL)
    d.text((85, 425), "#1 RECURRING PATTERN", font=_font(24, True), fill=ACCENT)

    top_name = str(top.get("name") or "Recurring Pattern").upper()
    name_lines = _wrap_lines(top_name, 22)
    name_y = 468
    for line in name_lines[:2]:
        f = _fit(d, line, 720, 61, 38, True)
        d.text((85, name_y), line, font=f, fill=TEXT)
        name_y += 66

    games_obs = int(top.get("games_observed") or 0)
    pos_obs = int(top.get("positions_observed") or 0)

    metric_y = max(605, name_y + 6)
    d.text((85, metric_y), f"{games_obs} / {games}", font=_font(86, True), fill=ACCENT)
    d.text((365, metric_y + 24), "games showed", font=_font(28, True), fill=MUTED)
    d.text((365, metric_y + 59), "this pattern", font=_font(28, True), fill=MUTED)

    d.line((85, metric_y + 133, 950, metric_y + 133), fill=LINE, width=2)
    d.text(
        (85, metric_y + 154),
        f"Evidence: {pos_obs} positions from your own games",
        font=_font(26, True),
        fill=TEXT,
    )

    # Training rule callout
    rule_top = metric_y + 205
    _rr(d, (78, rule_top, 966, rule_top + 128), radius=24, fill=SOFT, outline=ACCENT, width=2)
    d.text((110, rule_top + 19), "TRAINING RULE", font=_font(19, True), fill=ACCENT)
    rule = str(top.get("thinking_rule") or "")
    yy = rule_top + 50
    for line in _wrap_lines(rule, 47)[:2]:
        d.text((110, yy), line, font=_font(27, True), fill=TEXT)
        yy += 34

    # Decorative strategy arrows
    d.line((845, 500, 910, 445), fill="#2A6F9E", width=7)
    d.polygon([(910,445),(884,452),(902,470)], fill="#2A6F9E")
    d.line((850, 545, 930, 545), fill="#256484", width=7)
    d.polygon([(930,545),(904,532),(904,558)], fill="#256484")

    # Secondary signals
    d.text((70, 955), "ALSO SHOWING UP", font=_font(23, True), fill=MUTED)

    cards = [(second, 48), (third, 550)]
    for idx, (p, x0) in enumerate(cards, start=2):
        _rr(d, (x0, 995, x0 + 482, 1165), radius=26, fill=PANEL_ALT)
        d.text((x0 + 26, 1022), f"#{idx}", font=_font(24, True), fill=ACCENT)
        if p:
            nm = str(p.get("name") or "")
            lines = _wrap_lines(nm, 24)[:2]
            yy = 1020
            for line in lines:
                d.text((x0 + 96, yy), line, font=_font(29, True), fill=TEXT)
                yy += 35
            d.text(
                (x0 + 26, 1118),
                f"{p.get('games_observed',0)} games · {p.get('positions_observed',0)} positions",
                font=_font(21),
                fill=MUTED,
            )
        else:
            d.text((x0 + 90, 1030), "More games = stronger profile", font=_font(25, True), fill=TEXT)

    # CTA
    _rr(d, (48, 1202, 1032, 1318), radius=28, fill="#0B1932", outline=ACCENT, width=2)
    _draw_knight_mark(d, 103, 1260, 0.72)
    d.text((160, 1223), "Find the mistake YOU keep repeating.", font=_font(31, True), fill=TEXT)
    d.text((160, 1266), app_url, font=_font(24, True), fill=ACCENT_2)
    d.text((900, 1240), "FREE", font=_font(25, True), fill=ACCENT)

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
