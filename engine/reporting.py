
from html import escape

def _rate(errors, moves):
    return errors / moves if moves else 0.0

def phase_summary(analysis):
    counts = {"Opening":0,"Middlegame":0,"Endgame":0}
    for p in analysis.get("positions", []):
        counts[p["phase"]] += 1
    rows=[]
    for ph in ("Opening","Middlegame","Endgame"):
        m=analysis.get("phase_moves",{}).get(ph,0)
        e=counts.get(ph,0)
        rows.append({"phase":ph,"moves":m,"errors":e,"rate":_rate(e,m)})
    stable=min(rows,key=lambda x:x["rate"] if x["moves"] else 99)
    risk=max(rows,key=lambda x:x["rate"] if x["moves"] else -1)
    return rows, stable, risk

def player_summary(patterns, stable, risk):
    established=[p for p in patterns if p["confidence"] in ("high","medium")]
    if not established:
        return "This sample does not yet show a strong recurring decision pattern. More games will make the profile more reliable."
    top=established[0]
    second=established[1] if len(established)>1 else None
    text=f"Your clearest recurring signal is {top['name'].lower()}, observed across {top['games_observed']} games."
    if second:
        text+=f" A second recurring signal is {second['name'].lower()}."
    if stable["phase"] != risk["phase"]:
        text+=f" Your most stable phase in this sample is the {stable['phase'].lower()}, while the {risk['phase'].lower()} produced the highest significant-error rate."
    return text

def html_report(analysis, patterns):
    rows,stable,risk=phase_summary(analysis)
    player=escape(str(analysis.get("player","Player")))
    cards="".join(
        f"<div class='card'><h3>{i}. {escape(p['name'])}</h3><p>{escape(p['description'])}</p>"
        f"<p><b>{p['confidence'].title()} confidence</b> · {p['games_observed']} games · {p['positions_observed']} positions</p>"
        f"<p><b>Training rule:</b> {escape(p['thinking_rule'])}</p></div>"
        for i,p in enumerate(patterns[:5],1)
    )
    phase_rows="".join(f"<tr><td>{r['phase']}</td><td>{r['moves']}</td><td>{r['errors']}</td><td>{r['rate']*100:.1f}%</td></tr>" for r in rows)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{player} — Personal Chess Report</title>
<style>body{{font-family:Arial,sans-serif;max-width:900px;margin:40px auto;padding:0 24px;color:#20242d}}
.hero{{padding:30px;border:1px solid #ddd;border-radius:22px;background:#f8f8f8}}.card{{padding:18px;border:1px solid #ddd;border-radius:14px;margin:12px 0}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}</style></head>
<body><div class='hero'><small>PERSONAL CHESS REPORT</small><h1>{player}</h1><p>{escape(player_summary(patterns,stable,risk))}</p></div>
<h2>Decision profile</h2>{cards}<h2>Phase profile</h2><table><tr><th>Phase</th><th>Moves</th><th>Significant decisions</th><th>Rate</th></tr>{phase_rows}</table>
<p><small>Engine-grounded coaching report. Patterns are evidence-backed hypotheses from the analyzed game sample, not direct observations of your thought process.</small></p></body></html>"""
