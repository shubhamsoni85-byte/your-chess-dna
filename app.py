
import io, os, json, hashlib, html
from datetime import datetime
import requests
import streamlit as st
import chess, chess.pgn
import streamlit.components.v1 as components

from engine.analyzer import analyze_games
from engine.diagnosis import aggregate, TAXONOMY
from engine.reporting import phase_summary, player_summary, html_report
from engine.share_card import build_share_card

st.set_page_config(page_title="Your Chess DNA", page_icon="♟", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container{max-width:1180px;padding-top:1.1rem;padding-bottom:3rem}
#MainMenu,footer,header{visibility:hidden}
:root{--line:rgba(128,128,128,.18);--soft:rgba(128,128,128,.075)}
.hero{padding:2rem 2.15rem;border:1px solid var(--line);border-radius:24px;background:linear-gradient(135deg,var(--soft),rgba(127,127,127,.02));margin:.4rem 0 1rem}
.hero h1{font-size:clamp(2.3rem,5vw,4.6rem);line-height:1.02;letter-spacing:-.045em;margin:.25rem 0 .7rem;max-width:950px}
.hero p{font-size:1.08rem;line-height:1.6;opacity:.76;max-width:820px;margin:0}
.eyebrow{font-size:.76rem;font-weight:800;letter-spacing:.16em;opacity:.58;text-transform:uppercase}
.card{border:1px solid var(--line);border-radius:18px;padding:1.1rem 1.2rem;margin:.55rem 0;background:rgba(127,127,127,.025)}
.card h3{margin:.1rem 0 .3rem}
.signal{display:inline-block;border:1px solid var(--line);padding:.22rem .55rem;border-radius:999px;font-size:.76rem;margin:.15rem .25rem .15rem 0}
.big-number{font-size:2.05rem;font-weight:750;letter-spacing:-.03em}
.muted{opacity:.65}
.rule{padding:.8rem 1rem;border-left:4px solid rgba(128,128,128,.55);background:var(--soft);border-radius:0 12px 12px 0;margin-top:.6rem}
.cta{padding:1.15rem 1.2rem;border:1px solid var(--line);border-radius:18px;background:var(--soft);margin:.65rem 0}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
div[data-testid="stProgress"] > div > div > div{height:.55rem}
</style>
""", unsafe_allow_html=True)

def esc(x):
    return html.escape(str(x))

@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def chesscom_pgn(username, n):
    headers={"User-Agent":"PersonalChessCoachBeta/2.0"}
    r=requests.get(f"https://api.chess.com/pub/player/{username}/games/archives",headers=headers,timeout=15)
    if r.status_code==404:
        raise ValueError("Chess.com username not found.")
    r.raise_for_status()
    archives=r.json().get("archives",[])
    selected=[]
    for url in reversed(archives):
        rr=requests.get(url,headers=headers,timeout=20)
        rr.raise_for_status()
        for g in reversed(rr.json().get("games",[])):
            if g.get("rules")=="chess" and g.get("pgn"):
                selected.append(g["pgn"])
                if len(selected)>=n:
                    return "\n\n".join(reversed(selected))
    return "\n\n".join(reversed(selected))

def parse_games(pgn_text, player_name=None, limit=10):
    stream=io.StringIO(pgn_text)
    games=[]
    while len(games)<limit:
        g=chess.pgn.read_game(stream)
        if g is None: break
        if not list(g.mainline_moves()): continue
        w=g.headers.get("White",""); b=g.headers.get("Black","")
        color=None
        if player_name:
            if player_name.lower()==w.lower(): color=chess.WHITE
            elif player_name.lower()==b.lower(): color=chess.BLACK
            else: continue
        else:
            color=chess.WHITE
        games.append((g,color))
    return games

def board_html(fen, orientation="White", size=430):
    b=chess.Board(fen)
    files="abcdefgh"; ranks="12345678"
    rr=list(reversed(ranks)) if orientation=="White" else list(ranks)
    ff=list(files) if orientation=="White" else list(reversed(files))
    glyph={
        (chess.WHITE,chess.PAWN):"♙",(chess.WHITE,chess.KNIGHT):"♘",(chess.WHITE,chess.BISHOP):"♗",
        (chess.WHITE,chess.ROOK):"♖",(chess.WHITE,chess.QUEEN):"♕",(chess.WHITE,chess.KING):"♔",
        (chess.BLACK,chess.PAWN):"♟",(chess.BLACK,chess.KNIGHT):"♞",(chess.BLACK,chess.BISHOP):"♝",
        (chess.BLACK,chess.ROOK):"♜",(chess.BLACK,chess.QUEEN):"♛",(chess.BLACK,chess.KING):"♚",
    }
    cells=[]
    for r in rr:
        for f in ff:
            sq=chess.parse_square(f+r)
            pc=b.piece_at(sq)
            light=(chess.square_file(sq)+chess.square_rank(sq))%2==1
            bg="#eeeed2" if light else "#769656"
            g="" if not pc else glyph[(pc.color,pc.piece_type)]
            cells.append(f'<div style="background:{bg};display:flex;align-items:center;justify-content:center;font-size:{size//10}px;line-height:1">{g}</div>')
    return f'<div style="display:grid;grid-template-columns:repeat(8,1fr);width:{size}px;height:{size}px;border-radius:10px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.08)">{"".join(cells)}</div>'

def run_analysis(pgn_text, player, games_n):
    games=parse_games(pgn_text,player,games_n)
    if not games:
        raise ValueError("No matching games were found. Check the username/player name.")
    prog=st.progress(0,text="Preparing Stockfish…")
    def cb(i,total,msg):
        prog.progress(min(1.0,i/max(total,1)),text=msg)
    analysis=analyze_games(games,player or "PGN Player",cb)
    prog.empty()
    diagnosed,patterns=aggregate(analysis)
    analysis["positions"]=diagnosed
    analysis["patterns"]=patterns
    return analysis

def confidence_chip(p):
    return f'<span class="signal">{p["confidence"].title()} confidence</span>'

def phase_cards(report):
    rows,stable,risk=phase_summary(report)
    cols=st.columns(3)
    for col,row in zip(cols,rows):
        with col:
            pct=row["rate"]*100
            st.markdown(f"""<div class="card"><div class="eyebrow">{row["phase"]}</div>
            <div class="big-number">{pct:.1f}%</div><div class="muted">{row["errors"]} significant decisions / {row["moves"]} moves</div></div>""",unsafe_allow_html=True)
    return rows,stable,risk

def render_report(report):
    rows,stable,risk=phase_summary(report)
    summary=player_summary(report["patterns"],stable,risk)
    record=report.get("record",{})
    st.markdown(f"""<div class="hero"><div class="eyebrow">YOUR CHESS DNA</div>
    <h1>{esc(report["player"])}</h1><p>{esc(summary)}</p></div>""",unsafe_allow_html=True)

    a,b,c,d=st.columns(4)
    a.metric("Games analyzed",report["games_analyzed"])
    b.metric("Record",f'{record.get("wins",0)}W {record.get("losses",0)}L {record.get("draws",0)}D')
    b2=len(report.get("positions",[]))
    c.metric("Significant decisions",b2)
    d.metric("Most stable phase",stable["phase"])

    established=[p for p in report["patterns"] if p["confidence"] in ("high","medium")]
    st.markdown("## Your decision profile")
    st.caption("We only call a pattern recurring when it appears across multiple games. A single dramatic mistake is not enough.")
    if not established:
        st.info("This sample does not yet show a sufficiently repeated pattern. Analyze more games for a stronger profile.")
    for i,p in enumerate(established[:5],1):
        st.markdown(f"""<div class="card">
        <div class="eyebrow">#{i} RECURRING SIGNAL</div>
        <h3>{esc(p["name"])}</h3>
        {confidence_chip(p)}
        <span class="signal">{p["games_observed"]} games</span>
        <span class="signal">{p["positions_observed"]} positions</span>
        <p>{esc(p["description"])}</p>
        <div class="rule"><b>Training rule:</b> {esc(p["thinking_rule"])}</div>
        </div>""",unsafe_allow_html=True)

    st.markdown("## Where the errors happen")
    phase_cards(report)

    st.markdown("## Evidence from your own games")
    st.caption("These are the highest-impact examples behind the profile. Deep verification is used on the most consequential positions.")
    shown=sorted(report["positions"],key=lambda p:((p.get("verification") or {}).get("verified_drop") or p["win_probability_drop"]),reverse=True)[:6]
    for p in shown:
        loss=(p.get("verification") or {}).get("verified_drop") or p["win_probability_drop"]
        title=f'{p["phase"]} · move {p["move_number"]} · {p["played_move"]} · −{loss:.1f}%'
        with st.expander(title):
            l,r=st.columns([1.02,.98])
            with l:
                components.html(board_html(p["fen"],p["player_color"],400),height=415)
            with r:
                st.write(f"**Opponent:** {p['opponent']}")
                st.write(f"**You played:** `{p['played_move']}`")
                st.write(f"**Stronger move:** `{p['best_move']}`")
                if p.get("verification"):
                    st.write(f"**Verified played-move rank:** {p['verification']['played_rank_text']}")
                for d in p.get("diagnoses",[]):
                    st.markdown(f"**{TAXONOMY[d['label']]['name']}** · {int(d['confidence']*100)}% evidence confidence")
                    st.caption(d["evidence"])
                cands=p.get("candidate_moves",[])[:5]
                if cands:
                    st.write("**Top candidates:** "+", ".join(f"{c['san']} ({c['quality']})" for c in cands))

    st.markdown("## Your personalized training plan")
    priorities=established[:4] or report["patterns"][:4]
    for i,p in enumerate(priorities,1):
        st.markdown(f"""<div class="card"><div class="eyebrow">PRIORITY {i}</div>
        <h3>{esc(p["name"])}</h3><p>{esc(p["thinking_rule"])}</p></div>""",unsafe_allow_html=True)

    st.markdown("""<div class="cta"><b>Your report is not the finish line.</b><br>
    The Training tab turns the exact positions behind these patterns into exercises from your own games.</div>""",unsafe_allow_html=True)

    st.markdown("## Share your Chess DNA")
    st.caption("Turn your result into a social card. Post the card first; let people ask how you got it.")
    card_png = build_share_card(report, stable["phase"])
    st.image(card_png, caption="Your shareable Chess DNA card", use_container_width=True)
    st.download_button(
        "Download My Chess DNA (.png)",
        card_png,
        file_name=f'{report["player"]}_chess_dna.png',
        mime="image/png",
        type="primary",
        use_container_width=True,
    )

    report_html=html_report(report,report["patterns"])
    c1,c2=st.columns(2)
    with c1:
        st.download_button("Download shareable report (.html)",report_html,
                           file_name=f'{report["player"]}_chess_dna.html',mime="text/html",use_container_width=True)
    with c2:
        st.download_button("Download analysis data (.json)",json.dumps(report,indent=2),
                           file_name=f'{report["player"]}_analysis.json',mime="application/json",use_container_width=True)

def render_training(report):
    st.markdown("""<div class="hero"><div class="eyebrow">PERSONALIZED TRAINING</div>
    <h1>Train the decisions your own games exposed.</h1>
    <p>No generic puzzle feed. Every exercise below comes from a significant decision in the games you just analyzed.</p></div>""",unsafe_allow_html=True)
    patterns=[p for p in report["patterns"] if p["confidence"] in ("high","medium")]
    labels=[p["label"] for p in patterns[:4]]
    pool=[p for p in report["positions"] if p.get("primary_diagnosis") in labels] or report["positions"]
    pool=sorted(pool,key=lambda p:((p.get("verification") or {}).get("verified_drop") or p["win_probability_drop"]),reverse=True)[:12]
    if not pool:
        st.info("No training positions were generated from this sample.")
        return
    st.session_state.setdefault("train_idx",0)
    st.session_state.setdefault("train_score",0)
    st.session_state.setdefault("train_done",{})
    idx=min(st.session_state.train_idx,len(pool)-1)
    p=pool[idx]
    top,score=st.columns([2.2,.8])
    top.progress((idx+1)/len(pool),text=f"Exercise {idx+1}/{len(pool)}")
    score.metric("Solved",st.session_state.train_score)

    l,r=st.columns([1.05,.95],gap="large")
    with l:
        components.html(board_html(p["fen"],p["player_color"],430),height=445)
    with r:
        st.markdown(f"### You are {p['player_color']}")
        st.caption(f"{p['phase']} · move {p['move_number']} · vs {p['opponent']}")
        st.write("Choose the move you would play.")
        options=[c["san"] for c in p.get("candidate_moves",[])[:5]]
        if p["played_move"] not in options:
            options.append(p["played_move"])
        choice=st.radio("Candidate move",options,index=None,key=f"choice_{p['position_id']}")
        if st.button("Submit move",type="primary",use_container_width=True):
            cand=next((c for c in p.get("candidate_moves",[]) if c["san"]==choice),None)
            if not choice:
                st.warning("Choose a move first.")
            elif cand and cand["quality"] in ("BEST","EXCELLENT","GOOD"):
                if p["position_id"] not in st.session_state.train_done:
                    st.session_state.train_score+=1
                    st.session_state.train_done[p["position_id"]]=True
                if cand["quality"]=="BEST":
                    st.success(f"Strong. {choice} is Stockfish's top move.")
                else:
                    st.success(f"Good practical move. {choice} is rated {cand['quality'].lower()}; Stockfish slightly prefers {p['best_move']}.")
                if cand.get("line") and len(cand["line"])>=2:
                    st.write(f"**Likely reply:** {cand['line'][1]}")
            else:
                st.error("There is a stronger move. Compare the candidates again before revealing the answer.")
        with st.expander("Need a hint?"):
            primary=p.get("primary_diagnosis","calculation")
            st.write(TAXONOMY.get(primary,TAXONOMY["calculation"])["rule"])
        with st.expander("Reveal solution"):
            st.write(f"**Stronger move:** `{p['best_move']}`")
            st.write(f"Your game move was `{p['played_move']}`.")
            for d in p.get("diagnoses",[]):
                st.caption(f"{TAXONOMY[d['label']]['name']}: {d['evidence']}")
    nav1,nav2=st.columns(2)
    with nav1:
        if st.button("← Previous",disabled=idx==0,use_container_width=True):
            st.session_state.train_idx-=1;st.rerun()
    with nav2:
        if st.button("Next →",disabled=idx==len(pool)-1,use_container_width=True):
            st.session_state.train_idx+=1;st.rerun()

def render_method():
    st.markdown("""<div class="hero"><div class="eyebrow">HOW IT WORKS</div>
    <h1>Engine evidence first. Coaching interpretation second.</h1>
    <p>The app does not ask an LLM to invent chess explanations. Stockfish calculates; deterministic Python extracts evidence and only then assigns coaching signals.</p></div>""",unsafe_allow_html=True)
    steps=[
      ("1","Scan","Stockfish evaluates your recent games and records candidate moves, probability loss, phase, and board features."),
      ("2","Verify","The most consequential positions are rechecked at a higher search depth and the played move is explicitly ranked."),
      ("3","Diagnose","A coaching label is only assigned when a concrete feature supports it: a forcing reply, new loose material, king exposure, candidate rank, or irreversibility."),
      ("4","Aggregate","Repeated evidence is aggregated across games. One bad game cannot dominate the profile."),
      ("5","Train","Your recurring patterns become exercises from your own games."),
    ]
    for n,t,b in steps:
        st.markdown(f'<div class="card"><div class="eyebrow">STEP {n}</div><h3>{t}</h3><p>{b}</p></div>',unsafe_allow_html=True)
    st.info("The report describes evidence-backed coaching hypotheses from a limited game sample. It is not a direct observation of what you were thinking at the board.")

st.session_state.setdefault("page","Home")
st.session_state.setdefault("report",None)

nav=st.columns([2.4,1,1,1,1])
with nav[0]:
    st.markdown("### ♟ Your Chess DNA")
for col,name in zip(nav[1:],["Home","Report","Training","Method"]):
    with col:
        disabled=name in ("Report","Training") and st.session_state.report is None
        if st.button(name,use_container_width=True,disabled=disabled,key=f"nav_{name}"):
            st.session_state.page=name;st.rerun()

if st.session_state.page=="Home":
    st.markdown("""<div class="hero"><div class="eyebrow">FREE PERSONAL CHESS COACH</div>
    <h1>Stop guessing why you keep losing the same kind of position.</h1>
    <p>Enter your Chess.com username. We analyze your recent games, find decision patterns that repeat across games, show the evidence, and build a training plan from your own positions.</p></div>""",unsafe_allow_html=True)

    a,b,c=st.columns(3)
    with a: st.markdown('<div class="card"><b>Not just accuracy</b><br><span class="muted">See recurring decision patterns, not another engine score.</span></div>',unsafe_allow_html=True)
    with b: st.markdown('<div class="card"><b>Your own positions</b><br><span class="muted">Training comes directly from games you actually played.</span></div>',unsafe_allow_html=True)
    with c: st.markdown('<div class="card"><b>Free beta</b><br><span class="muted">No account, subscription, or paid AI API required.</span></div>',unsafe_allow_html=True)

    tab1,tab2=st.tabs(["Chess.com username","Upload PGN"])
    with tab1:
        username=st.text_input("Chess.com username",placeholder="e.g. SHUBHAM85")
        games_n=st.slider("Recent games",5,15,10)
        if st.button("Reveal my Chess DNA →",type="primary",use_container_width=True):
            if not username.strip():
                st.warning("Enter a Chess.com username.")
            else:
                try:
                    with st.spinner("Fetching recent public games…"):
                        pgn=chesscom_pgn(username.strip(),games_n)
                    report=run_analysis(pgn,username.strip(),games_n)
                    st.session_state.report=report
                    st.session_state.page="Report"
                    st.session_state.train_idx=0
                    st.session_state.train_score=0
                    st.session_state.train_done={}
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    with tab2:
        up=st.file_uploader("PGN file",type=["pgn"])
        player=st.text_input("Player username/name exactly as it appears in the PGN")
        games_n2=st.slider("Games to analyze",5,15,10,key="pgn_n")
        if st.button("Analyze uploaded games →",use_container_width=True):
            if not up:
                st.warning("Upload a PGN file.")
            elif not player.strip():
                st.warning("Enter the player name as it appears in the PGN.")
            else:
                try:
                    txt=up.getvalue().decode("utf-8",errors="replace")
                    report=run_analysis(txt,player.strip(),games_n2)
                    st.session_state.report=report;st.session_state.page="Report";st.rerun()
                except Exception as e:
                    st.error(str(e))
    st.caption("Public beta · No account required · Analysis is kept in your current browser session. Chess.com ingestion uses publicly available game data; PGN upload is always available.")

elif st.session_state.page=="Report":
    render_report(st.session_state.report)
elif st.session_state.page=="Training":
    render_training(st.session_state.report)
else:
    render_method()
