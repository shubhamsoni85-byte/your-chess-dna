
from collections import defaultdict

TAXONOMY = {
    "opponent_response_calculation": {
        "name": "Opponent Response Calculation",
        "short": "You sometimes choose a move before fully stress-testing the opponent's strongest forcing reply.",
        "rule": "Before committing, calculate the opponent's strongest check, capture, and direct threat.",
    },
    "candidate_move_selection": {
        "name": "Candidate Move Selection",
        "short": "Stronger alternatives were available, suggesting the candidate set deserves more deliberate comparison.",
        "rule": "Generate at least two serious candidates before choosing one.",
    },
    "piece_safety": {
        "name": "Piece Safety",
        "short": "Some costly decisions increased the number or value of loose pieces.",
        "rule": "After choosing a move, scan every piece that can be captured immediately.",
    },
    "forcing_moves": {
        "name": "Forcing Moves",
        "short": "Checks and captures were sometimes underweighted when they should have led the calculation.",
        "rule": "Scan checks and forcing captures before settling on a quiet move.",
    },
    "premature_commitment": {
        "name": "Irreversible Decisions",
        "short": "A number of costly errors came from irreversible moves when a more flexible alternative existed.",
        "rule": "Before a pawn push, capture, or commitment, ask what flexibility you are giving up.",
    },
    "king_safety": {
        "name": "King Safety",
        "short": "Some decisions measurably increased king exposure.",
        "rule": "Before committing, compare king exposure before and after the move.",
    },
    "positional_understanding": {
        "name": "Positional Decision Making",
        "short": "Some non-forcing positions were mishandled without a clear tactical trigger.",
        "rule": "When there is no forcing move, improve your least active piece and compare quiet candidates.",
    },
    "opening_understanding": {
        "name": "Opening Decisions",
        "short": "Several early-game decisions lost value without an immediate tactical necessity.",
        "rule": "In the opening, prioritize development, center control, and king safety unless tactics override them.",
    },
    "endgame_technique": {
        "name": "Endgame Technique",
        "short": "Some endgame decisions lost value without being explained by an immediate tactical oversight.",
        "rule": "In endgames, compare king activity, pawn races, and simplification before committing.",
    },
    "conversion_technique": {
        "name": "Conversion Technique",
        "short": "Some favorable positions lost a meaningful part of their advantage.",
        "rule": "When better, reduce counterplay before trying to force the win.",
    },
    "calculation": {
        "name": "Calculation",
        "short": "Concrete calculation errors remain after the more specific signals are accounted for.",
        "rule": "Calculate one move deeper than feels necessary in forcing positions.",
    },
}

def _loose_value(items):
    return sum(int(x.get("value", 0)) for x in (items or []))

def _rank(position):
    v = position.get("verification") or {}
    if v.get("played_rank") is not None:
        return v["played_rank"]
    uci = position.get("played_move_uci")
    for c in position.get("candidate_moves", []):
        if c.get("uci") == uci:
            return c.get("rank")
    return None

def diagnose_position(p):
    loss = (p.get("verification") or {}).get("verified_drop")
    if loss is None:
        loss = p.get("win_probability_drop", 0)
    before = p.get("board_features_before", {})
    after = p.get("board_features_after", {})
    move = p.get("played_move_features", {})
    best = p.get("best_move_features", {})
    reply = p.get("first_response") or {}
    complexity = p.get("candidate_complexity") or {}
    rank = _rank(p)
    labels = []

    def add(label, confidence, evidence):
        if confidence >= 0.55 and label not in {x["label"] for x in labels}:
            labels.append({"label": label, "confidence": round(confidence, 2), "evidence": evidence})

    # Opponent-response calculation requires an observable forcing reply.
    if loss >= 12 and reply.get("is_forcing"):
        forcing = "check" if reply.get("is_check") else "capture"
        add("opponent_response_calculation",
            min(.96, .68 + loss/180),
            f"After {p['played_move']}, Stockfish's strongest reply {reply.get('san')} is a forcing {forcing}; the decision lost about {loss:.1f}% practical winning probability.")

    # Piece safety requires a measurable increase in loose material.
    before_loose = before.get("player_loose_pieces", [])
    after_loose = after.get("player_loose_pieces", [])
    delta_loose = _loose_value(after_loose) - _loose_value(before_loose)
    if loss >= 8 and delta_loose >= 2:
        add("piece_safety", min(.95, .68 + .07*delta_loose),
            f"Loose-piece value increased by {delta_loose} after the move ({len(before_loose)} loose before, {len(after_loose)} after).")

    # Candidate selection is strongest when multiple healthy alternatives existed and the played move ranked poorly.
    near = complexity.get("near_equal_moves", 0)
    only_move = complexity.get("only_move_signal", False)
    if loss >= 8 and not only_move and rank is not None and rank >= 3 and near >= 2:
        add("candidate_move_selection", min(.93, .62 + .07*min(rank,5) + .02*near),
            f"The played move ranked #{rank} while {near} candidate moves were within 5% of the best line.")
    elif loss >= 12 and not only_move and rank is None and near >= 2:
        add("candidate_move_selection", .78,
            f"The played move fell outside the stored top candidates while {near} strong alternatives were close to the best line.")

    # Forcing moves only if best move itself is forcing and played move is not.
    if loss >= 8 and (best.get("gives_check") or best.get("is_capture")) and not (move.get("gives_check") or move.get("is_capture")):
        kind = "check" if best.get("gives_check") else "capture"
        add("forcing_moves", .76 if loss < 20 else .86,
            f"The strongest move {p['best_move']} was a forcing {kind}, while {p['played_move']} was not forcing.")

    # Irreversible decision requires observable irreversibility plus a flexible best move.
    if loss >= 8 and move.get("is_irreversible") and not best.get("is_irreversible"):
        add("premature_commitment", .72 if loss < 20 else .82,
            f"{p['played_move']} was irreversible, while the stronger move {p['best_move']} preserved more flexibility.")

    # King safety uses before/after board features.
    kb = before.get("player_king_safety", {})
    ka = after.get("player_king_safety", {})
    ring_delta = ka.get("attacked_ring",0) - kb.get("attacked_ring",0)
    shield_delta = kb.get("pawn_shield",0) - ka.get("pawn_shield",0)
    if loss >= 8 and (ring_delta >= 2 or shield_delta >= 1):
        add("king_safety", min(.92, .67 + .07*ring_delta + .06*shield_delta),
            f"King exposure increased: attacked king-ring squares changed by {ring_delta:+d} and pawn-shield count by {-shield_delta:+d}.")

    specific = {x["label"] for x in labels}
    tactical = bool(specific & {"opponent_response_calculation","piece_safety","forcing_moves","king_safety"})

    # Conversion only when the player was clearly better before the move.
    if p.get("phase") == "Endgame" and p.get("win_probability_before",0) >= 70 and loss >= 10:
        add("conversion_technique", .72 if tactical else .84,
            f"The position began with about {p['win_probability_before']:.1f}% practical winning probability and lost roughly {loss:.1f}%.")

    # Phase labels are fallbacks, not automatic phase tags.
    if p.get("phase") == "Endgame" and loss >= 8 and not tactical:
        add("endgame_technique", .68,
            "The endgame loss was not explained by an immediate forcing-reply, loose-piece, or king-safety signal.")
    if p.get("phase") == "Opening" and 8 <= loss < 20 and not tactical and not move.get("is_capture"):
        add("opening_understanding", .63,
            "The early-game loss was non-forcing and was not explained by an immediate tactical safety signal.")
    if p.get("phase") == "Middlegame" and 8 <= loss < 20 and not tactical and not move.get("is_capture"):
        add("positional_understanding", .61,
            "The loss occurred in a non-forcing middlegame decision without a stronger tactical signal.")

    if not labels:
        add("calculation", .60 if loss < 20 else .70,
            f"The move lost about {loss:.1f}% practical winning probability, but the deterministic feature checks do not support a narrower label.")

    labels.sort(key=lambda x: x["confidence"], reverse=True)
    return labels[:3]

def aggregate(analysis):
    evidence = defaultdict(list)
    per_game = defaultdict(lambda: defaultdict(float))
    diagnosed = []
    for p in analysis.get("positions", []):
        labels = diagnose_position(p)
        q = dict(p)
        q["diagnoses"] = labels
        q["primary_diagnosis"] = labels[0]["label"] if labels else "calculation"
        diagnosed.append(q)
        for d in labels:
            label = d["label"]
            evidence[label].append({
                "game_number": p["game_number"],
                "position_id": p["position_id"],
                "confidence": d["confidence"],
                "evidence": d["evidence"],
                "move_number": p["move_number"],
                "phase": p["phase"],
                "played_move": p["played_move"],
                "best_move": p["best_move"],
                "loss": (p.get("verification") or {}).get("verified_drop") or p["win_probability_drop"],
            })
            per_game[label][p["game_number"]] = max(per_game[label][p["game_number"]], d["confidence"])

    patterns = []
    for label, items in evidence.items():
        games = len(per_game[label])
        score = round(sum(per_game[label].values()), 2)
        avg = round(sum(x["confidence"] for x in items) / len(items), 2)
        band = "high" if games >= 4 and score >= 2.4 else "medium" if games >= 3 and score >= 1.5 else "possible"
        patterns.append({
            "label": label,
            "name": TAXONOMY[label]["name"],
            "description": TAXONOMY[label]["short"],
            "thinking_rule": TAXONOMY[label]["rule"],
            "confidence": band,
            "games_observed": games,
            "positions_observed": len(items),
            "cross_game_score": score,
            "average_confidence": avg,
            "evidence": sorted(items, key=lambda x: (x["confidence"], x["loss"]), reverse=True)[:5],
        })
    patterns.sort(key=lambda x: (x["cross_game_score"], x["games_observed"], x["positions_observed"]), reverse=True)
    return diagnosed, patterns
