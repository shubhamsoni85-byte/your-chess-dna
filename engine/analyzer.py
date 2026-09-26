
import math
import os
import shutil
from collections import Counter
import chess
import chess.engine
import chess.pgn

SCAN_DEPTH = 13
CANDIDATE_COUNT = 5
VERIFY_DEPTH = 18
VERIFY_MULTIPV = 10
MIN_SIGNIFICANT_DROP = 8.0
MAX_VERIFY_POSITIONS = 12

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

def stockfish_path():
    candidates = [
        os.getenv("STOCKFISH_PATH"),
        shutil.which("stockfish"),
        r"C:\stockfish\stockfish-windows-x86-64-universal.exe",
        "/usr/games/stockfish",
        "/usr/local/bin/stockfish",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None

def _score_cp(score, color):
    pov = score.pov(color)
    if pov.is_mate():
        mate = pov.mate()
        return 100000 if mate and mate > 0 else -100000
    return pov.score(mate_score=100000) or 0

def probability_from_score(score, color):
    pov = score.pov(color)
    if pov.is_mate():
        return 100.0 if (pov.mate() or 0) > 0 else 0.0
    cp = pov.score(mate_score=100000) or 0
    pawns = max(-12.0, min(12.0, cp / 100.0))
    return 100.0 / (1.0 + math.exp(-0.9 * pawns))

def eval_text(score, color):
    pov = score.pov(color)
    if pov.is_mate():
        m = pov.mate()
        return f"M{m}" if m is not None else "Mate"
    cp = pov.score(mate_score=100000) or 0
    return f"{cp / 100:+.2f}"

def phase(board):
    if board.fullmove_number <= 10:
        return "Opening"
    non_pawn = 0
    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        for color in (chess.WHITE, chess.BLACK):
            non_pawn += len(board.pieces(pt, color)) * PIECE_VALUES[pt]
    return "Endgame" if non_pawn <= 20 else "Middlegame"

def attacked_undefended(board, color):
    out = []
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if not p or p.color != color or p.piece_type == chess.KING:
            continue
        attacked = board.is_attacked_by(not color, sq)
        defended = board.is_attacked_by(color, sq)
        if attacked and not defended:
            out.append({
                "square": chess.square_name(sq),
                "piece": chess.piece_name(p.piece_type),
                "value": PIECE_VALUES[p.piece_type],
            })
    return out

def material_snapshot(board, color):
    own = Counter()
    opp = Counter()
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if not p:
            continue
        name = chess.piece_name(p.piece_type)
        (own if p.color == color else opp)[name] += 1
    own_value = sum(PIECE_VALUES[pt] * len(board.pieces(pt, color)) for pt in PIECE_VALUES)
    opp_value = sum(PIECE_VALUES[pt] * len(board.pieces(pt, not color)) for pt in PIECE_VALUES)
    return {
        "own": dict(own),
        "opponent": dict(opp),
        "material_balance": own_value - opp_value,
    }

def pawn_structure(board, color):
    pawns = list(board.pieces(chess.PAWN, color))
    files = Counter(chess.square_file(sq) for sq in pawns)
    doubled = sum(max(0, n - 1) for n in files.values())
    isolated = 0
    for sq in pawns:
        f = chess.square_file(sq)
        neighbors = [nf for nf in (f - 1, f + 1) if 0 <= nf <= 7]
        if not any(files[nf] for nf in neighbors):
            isolated += 1
    return {"doubled": doubled, "isolated": isolated}

def king_safety(board, color):
    king = board.king(color)
    if king is None:
        return {"king_square": None, "attacked_ring": 0, "pawn_shield": 0}
    attacked = 0
    for sq in chess.SQUARES:
        if chess.square_distance(king, sq) <= 1 and board.is_attacked_by(not color, sq):
            attacked += 1
    kf, kr = chess.square_file(king), chess.square_rank(king)
    forward = 1 if color == chess.WHITE else -1
    target_rank = kr + forward
    shield = 0
    if 0 <= target_rank <= 7:
        for f in range(max(0, kf - 1), min(7, kf + 1) + 1):
            pc = board.piece_at(chess.square(f, target_rank))
            if pc and pc.color == color and pc.piece_type == chess.PAWN:
                shield += 1
    return {
        "king_square": chess.square_name(king),
        "attacked_ring": attacked,
        "pawn_shield": shield,
    }

def move_features(board, move):
    piece = board.piece_at(move.from_square)
    return {
        "piece": chess.piece_name(piece.piece_type) if piece else None,
        "is_capture": board.is_capture(move),
        "gives_check": board.gives_check(move),
        "is_pawn_move": bool(piece and piece.piece_type == chess.PAWN),
        "is_castling": board.is_castling(move),
        "is_promotion": move.promotion is not None,
        "is_irreversible": board.is_irreversible(move),
    }

def board_features(board, color):
    return {
        "material": material_snapshot(board, color),
        "player_loose_pieces": attacked_undefended(board, color),
        "opponent_loose_pieces": attacked_undefended(board, not color),
        "player_pawn_structure": pawn_structure(board, color),
        "opponent_pawn_structure": pawn_structure(board, not color),
        "player_king_safety": king_safety(board, color),
        "opponent_king_safety": king_safety(board, not color),
        "legal_checks": sum(1 for m in board.legal_moves if board.gives_check(m)),
        "legal_captures": sum(1 for m in board.legal_moves if board.is_capture(m)),
    }

def quality_from_loss(loss, is_best=False):
    if is_best:
        return "BEST"
    if loss <= 2:
        return "EXCELLENT"
    if loss <= 5:
        return "GOOD"
    if loss < 8:
        return "INACCURACY"
    if loss < 20:
        return "MISTAKE"
    return "BLUNDER"

def candidate_complexity(candidates):
    if not candidates:
        return {"spread": None, "near_equal_moves": 0, "only_move_signal": False}
    probs = [c["probability"] for c in candidates]
    best = probs[0]
    near = sum(1 for p in probs if best - p <= 5.0)
    spread = round(max(probs) - min(probs), 1)
    return {
        "spread": spread,
        "near_equal_moves": near,
        "only_move_signal": near == 1 and spread >= 20,
    }

def _candidate_moves(board, infos, color):
    if not isinstance(infos, list):
        infos = [infos]
    if not infos:
        return []
    best_prob = probability_from_score(infos[0]["score"], color)
    out = []
    for rank, info in enumerate(infos, 1):
        pv = info.get("pv") or []
        if not pv or pv[0] not in board.legal_moves:
            continue
        root = pv[0]
        prob = probability_from_score(info["score"], color)
        line_board = board.copy()
        san_line = []
        for m in pv[:5]:
            if m not in line_board.legal_moves:
                break
            san_line.append(line_board.san(m))
            line_board.push(m)
        loss = max(0.0, best_prob - prob)
        out.append({
            "rank": rank,
            "uci": root.uci(),
            "san": board.san(root),
            "probability": round(prob, 1),
            "loss_vs_best": round(loss, 1),
            "quality": quality_from_loss(loss, rank == 1),
            "features": move_features(board, root),
            "line": san_line,
        })
    return out

def _forcing_reply(engine, after_board, player_color):
    info = engine.analyse(after_board, chess.engine.Limit(depth=SCAN_DEPTH))
    pv = info.get("pv") or []
    if not pv:
        return None
    reply = pv[0]
    feats = move_features(after_board, reply)
    return {
        "uci": reply.uci(),
        "san": after_board.san(reply),
        "is_check": feats["gives_check"],
        "is_capture": feats["is_capture"],
        "is_forcing": feats["gives_check"] or feats["is_capture"],
    }

def _verify(engine, before, played, color):
    legal_count = before.legal_moves.count()
    mpv = min(VERIFY_MULTIPV, legal_count)
    infos = engine.analyse(before, chess.engine.Limit(depth=VERIFY_DEPTH), multipv=mpv)
    if not isinstance(infos, list):
        infos = [infos]
    ranked = []
    played_rank = None
    best_prob = None
    for rank, info in enumerate(infos, 1):
        pv = info.get("pv") or []
        if not pv:
            continue
        prob = probability_from_score(info["score"], color)
        if best_prob is None:
            best_prob = prob
        ranked.append({"rank": rank, "uci": pv[0].uci(), "san": before.san(pv[0]), "probability": round(prob, 1)})
        if pv[0] == played:
            played_rank = rank
    exact = engine.analyse(before, chess.engine.Limit(depth=VERIFY_DEPTH), root_moves=[played])
    played_prob = probability_from_score(exact["score"], color)
    return {
        "depth": VERIFY_DEPTH,
        "played_rank": played_rank,
        "played_rank_text": str(played_rank) if played_rank is not None else f">{mpv}",
        "best_probability": round(best_prob, 1) if best_prob is not None else None,
        "played_probability": round(played_prob, 1),
        "verified_drop": round(max(0.0, (best_prob or played_prob) - played_prob), 1),
        "top_moves": ranked[:8],
    }

def analyze_games(games, username, progress_callback=None):
    path = stockfish_path()
    if not path:
        raise RuntimeError("Stockfish was not found. Install Stockfish or set STOCKFISH_PATH.")
    engine = chess.engine.SimpleEngine.popen_uci(path)
    all_positions = []
    phase_moves = Counter()
    results = Counter()
    game_meta = []
    try:
        total = len(games)
        for gi, (game, color) in enumerate(games, 1):
            board = game.board()
            result = game.headers.get("Result", "*")
            if result == "1/2-1/2":
                results["draws"] += 1
            elif (result == "1-0" and color == chess.WHITE) or (result == "0-1" and color == chess.BLACK):
                results["wins"] += 1
            elif result in ("1-0", "0-1"):
                results["losses"] += 1
            opponent = game.headers.get("Black" if color == chess.WHITE else "White", "Unknown")
            local_errors = 0
            for ply, played in enumerate(game.mainline_moves()):
                if board.turn != color:
                    board.push(played)
                    continue
                ph = phase(board)
                phase_moves[ph] += 1
                before = board.copy()
                infos = engine.analyse(before, chess.engine.Limit(depth=SCAN_DEPTH), multipv=CANDIDATE_COUNT)
                if not isinstance(infos, list):
                    infos = [infos]
                candidates = _candidate_moves(before, infos, color)
                if not candidates:
                    board.push(played)
                    continue
                best_prob = candidates[0]["probability"]
                played_san = before.san(played)
                best_san = candidates[0]["san"]
                before_features = board_features(before, color)
                played_feats = move_features(before, played)
                fen = before.fen()
                board.push(played)
                after_info = engine.analyse(board, chess.engine.Limit(depth=SCAN_DEPTH))
                after_prob = probability_from_score(after_info["score"], color)
                loss = round(max(0.0, best_prob - after_prob), 1)
                if loss >= MIN_SIGNIFICANT_DROP:
                    local_errors += 1
                    after_features = board_features(board, color)
                    reply = _forcing_reply(engine, board, color)
                    cand_match = next((c for c in candidates if c["uci"] == played.uci()), None)
                    all_positions.append({
                        "position_id": f"g{gi}_p{ply+1}",
                        "game_number": gi,
                        "move_number": before.fullmove_number,
                        "player_color": "White" if color == chess.WHITE else "Black",
                        "opponent": opponent,
                        "result": result,
                        "phase": ph,
                        "fen": fen,
                        "played_move": played_san,
                        "played_move_uci": played.uci(),
                        "best_move": best_san,
                        "best_move_uci": candidates[0]["uci"],
                        "win_probability_before": round(best_prob, 1),
                        "win_probability_after": round(after_prob, 1),
                        "win_probability_drop": loss,
                        "played_move_quality": cand_match["quality"] if cand_match else quality_from_loss(loss),
                        "candidate_moves": candidates,
                        "candidate_complexity": candidate_complexity(candidates),
                        "played_move_features": played_feats,
                        "best_move_features": candidates[0]["features"],
                        "board_features_before": before_features,
                        "board_features_after": after_features,
                        "first_response": reply,
                        "verification": None,
                    })
            game_meta.append({
                "game_number": gi,
                "opponent": opponent,
                "result": result,
                "significant_positions": local_errors,
            })
            if progress_callback:
                progress_callback(gi, total, f"Scanning game {gi}/{total}")
        # High-depth verification only for the most consequential positions.
        verify_targets = sorted(
            all_positions,
            key=lambda p: (p["win_probability_drop"], p["candidate_complexity"]["only_move_signal"]),
            reverse=True,
        )[:MAX_VERIFY_POSITIONS]
        for vi, pos in enumerate(verify_targets, 1):
            before = chess.Board(pos["fen"])
            played = chess.Move.from_uci(pos["played_move_uci"])
            color = chess.WHITE if pos["player_color"] == "White" else chess.BLACK
            pos["verification"] = _verify(engine, before, played, color)
            if progress_callback:
                progress_callback(vi, len(verify_targets), f"Verifying critical position {vi}/{len(verify_targets)}")
    finally:
        engine.quit()
    return {
        "player": username,
        "games_analyzed": len(games),
        "record": dict(results),
        "phase_moves": dict(phase_moves),
        "positions": all_positions,
        "games": game_meta,
        "settings": {
            "scan_depth": SCAN_DEPTH,
            "candidate_count": CANDIDATE_COUNT,
            "verify_depth": VERIFY_DEPTH,
            "verified_positions_max": MAX_VERIFY_POSITIONS,
            "significant_drop_threshold": MIN_SIGNIFICANT_DROP,
        },
    }
