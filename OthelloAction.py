import time
import OthelloLogic

BOARD_SIZE = 8
BLACK = 1
WHITE = -1
EMPTY = 0

CORNERS = {(0, 0), (0, 7), (7, 0), (7, 7)}
X_SQUARES = {(1, 1), (1, 6), (6, 1), (6, 6)}
C_SQUARES = {(0, 1), (1, 0), (0, 6), (1, 7), (6, 0), (7, 1), (6, 7), (7, 6)}
EDGES = {(0, i) for i in range(8)} | {(7, i) for i in range(8)} | {(i, 0) for i in range(8)} | {(i, 7) for i in range(8)}

DEPTH_EARLY = 4
DEPTH_MID = 5
DEPTH_LATE = 6
DEPTH_VERY_LATE = 7

ENDGAME_SOLVE_EMPTY = 10
ENDGAME_SOLVE_BRANCH_MAX = 7

Q_DEPTH = 2

PASS_BONUS = 2500

NODE_LIMIT = 220000

LOCKED_CORNER_EDGE_W = 900
LOCKED_FULL_EDGE_W = 700
LOCKED_FULL_EDGE_ENABLE_EMPTY = 12

OBS_ENABLE = True
OBS_MAX = 12
OBS_WEIGHT = 0.25
OBS_XC_BONUS_PEN = 0.25

STAT_ENABLE = True

_stat = {
    "t0": 0.0,
    "time_ms": 0.0,
    "nodes": 0,
    "getMoves": 0,
    "getMoves_hit": 0,
    "execute": 0,
    "execute_hit": 0,
}

CACHE_ENABLE = True
MOVES_CACHE_MAX = 200000
EXEC_CACHE_MAX = 120000

_moves_cache = {}
_exec_cache = {}

_tt = {}
_exact_tt = {}

_node = 0

def fast_copy(board):
    return [row[:] for row in board]

def board_key(board):
    return tuple(tuple(r) for r in board)

def _cache_maybe_clear():
    if len(_moves_cache) > MOVES_CACHE_MAX:
        _moves_cache.clear()
    if len(_exec_cache) > EXEC_CACHE_MAX:
        _exec_cache.clear()

def get_moves(board, color):
    if STAT_ENABLE:
        _stat["getMoves"] += 1

    if not CACHE_ENABLE:
        return OthelloLogic.getMoves(board, color, BOARD_SIZE)

    k = (board_key(board), color)
    v = _moves_cache.get(k)
    if v is not None:
        if STAT_ENABLE:
            _stat["getMoves_hit"] += 1
        return v

    v = OthelloLogic.getMoves(board, color, BOARD_SIZE)
    _moves_cache[k] = v
    _cache_maybe_clear()
    return v

def execute(board, move, color):
    if STAT_ENABLE:
        _stat["execute"] += 1

    if not CACHE_ENABLE:
        nb = fast_copy(board)
        return OthelloLogic.execute(nb, move, color, BOARD_SIZE)

    k = (board_key(board), color, move[0], move[1])
    v = _exec_cache.get(k)
    if v is not None:
        if STAT_ENABLE:
            _stat["execute_hit"] += 1
        return fast_copy(v)

    nb = fast_copy(board)
    nb = OthelloLogic.execute(nb, move, color, BOARD_SIZE)
    _exec_cache[k] = nb
    _cache_maybe_clear()
    return fast_copy(nb)

def count_discs(board):
    b = w = e = 0
    for r in range(8):
        for c in range(8):
            if board[r][c] == BLACK:
                b += 1
            elif board[r][c] == WHITE:
                w += 1
            else:
                e += 1
    return b, w, e

def detect_new_game(board):
    b, w, e = count_discs(board)
    return (b + w) <= 4 and e >= 60

def infer_my_color(board):
    b, w, _ = count_discs(board)
    return BLACK if b <= w else WHITE

def is_terminal(board):
    return (len(get_moves(board, BLACK)) == 0 and len(get_moves(board, WHITE)) == 0)

def final_diff(board, me):
    b, w, _ = count_discs(board)
    return (b - w) if me == BLACK else (w - b)

def gives_opponent_corner(board_after, opp_color):
    opp_moves = get_moves(board_after, opp_color)
    return any(tuple(m) in CORNERS for m in opp_moves)

def detect_opp_placed(prev_board, cur_board, my_color):
    if prev_board is None:
        return None
    opp = -my_color
    for r in range(8):
        for c in range(8):
            if prev_board[r][c] == EMPTY and cur_board[r][c] == opp:
                return (r, c)
    return None


def stable_edge_score(board, me):
    def scan(line):
        c = 0
        for v in line:
            if v == me:
                c += 1
            else:
                break
        return c

    s = 0
    if board[0][0] == me:
        s += 300 * scan(board[0])
        s += 300 * scan([board[i][0] for i in range(8)])
    if board[0][7] == me:
        s += 300 * scan(board[0][::-1])
        s += 300 * scan([board[i][7] for i in range(8)])
    if board[7][0] == me:
        s += 300 * scan(board[7])
        s += 300 * scan([board[i][0] for i in range(7, -1, -1)])
    if board[7][7] == me:
        s += 300 * scan(board[7][::-1])
        s += 300 * scan([board[i][7] for i in range(7, -1, -1)])
    return s

def count_locked_corner_edges(board, me):
    def scan(line):
        c = 0
        for v in line:
            if v == me:
                c += 1
            else:
                break
        return c

    locked = 0
    if board[0][0] == me:
        locked += scan(board[0])
        locked += scan([board[i][0] for i in range(8)])
    if board[0][7] == me:
        locked += scan(board[0][::-1])
        locked += scan([board[i][7] for i in range(8)])
    if board[7][0] == me:
        locked += scan(board[7])
        locked += scan([board[i][0] for i in range(7, -1, -1)])
    if board[7][7] == me:
        locked += scan(board[7][::-1])
        locked += scan([board[i][7] for i in range(7, -1, -1)])
    return locked

def count_locked_full_edges(board, me):
    def full(line):
        return EMPTY not in line

    locked = 0
    if board[0][0] != EMPTY and board[0][7] != EMPTY and full(board[0]):
        locked += board[0].count(me)
    if board[7][0] != EMPTY and board[7][7] != EMPTY and full(board[7]):
        locked += board[7].count(me)

    left = [board[i][0] for i in range(8)]
    right = [board[i][7] for i in range(8)]
    if board[0][0] != EMPTY and board[7][0] != EMPTY and full(left):
        locked += left.count(me)
    if board[0][7] != EMPTY and board[7][7] != EMPTY and full(right):
        locked += right.count(me)
    return locked


def eval_edge_line(line, me):
    opp = -me
    score = 0
    empties = line.count(EMPTY)

    if line[0] == me:
        c = 0
        for v in line:
            if v == me:
                c += 1
            else:
                break
        score += 200 * c
    if line[-1] == me:
        c = 0
        for v in reversed(line):
            if v == me:
                c += 1
            else:
                break
        score += 200 * c

    if line[0] == opp:
        score -= 150 * line.count(me)
    if line[-1] == opp:
        score -= 150 * line.count(me)

    if empties <= 2:
        score -= 300
    return score

def edge_shape_score(board, me):
    s = 0
    s += eval_edge_line(board[0], me)
    s += eval_edge_line(board[7], me)
    s += eval_edge_line([board[i][0] for i in range(8)], me)
    s += eval_edge_line([board[i][7] for i in range(8)], me)
    return s

def evaluate(board, me):
    opp = -me
    b, w, e = count_discs(board)

    my_moves = get_moves(board, me)
    my_can_corner_now = any(tuple(m) in CORNERS for m in my_moves)

    diff = (b - w) if me == BLACK else (w - b)
    disc = diff * (0.2 + (64 - e) / 64 * 3.2)

    oppm = len(get_moves(board, opp))
    mobility = 60 * (len(my_moves) - oppm)

    corner = 0
    for r, c in CORNERS:
        if board[r][c] == me:
            corner += 7000
        elif board[r][c] == opp:
            corner -= 7000

    edge = 0
    for r, c in EDGES:
        if (r, c) in CORNERS:
            continue
        if board[r][c] == me:
            edge += 120
        elif board[r][c] == opp:
            edge -= 120

    stable = stable_edge_score(board, me) - stable_edge_score(board, opp)
    locked_corner = LOCKED_CORNER_EDGE_W * (
        count_locked_corner_edges(board, me) - count_locked_corner_edges(board, opp)
    )

    locked_full = 0
    if e <= LOCKED_FULL_EDGE_ENABLE_EMPTY:
        locked_full = LOCKED_FULL_EDGE_W * (
            count_locked_full_edges(board, me) - count_locked_full_edges(board, opp)
        )

    obs_scale = 0.0
    if OBS_ENABLE and hasattr(getAction, "opp_xc_total") and hasattr(getAction, "opp_xc_hits"):
        t = max(1, min(OBS_MAX, getAction.opp_xc_total))
        rate = getAction.opp_xc_hits / t
        obs_scale = OBS_WEIGHT * rate

    x_pen_base = 3500 * (1.0 + OBS_XC_BONUS_PEN * obs_scale)
    c_pen_base = 1600 * (1.0 + OBS_XC_BONUS_PEN * obs_scale)

    donation = 0

    for r, c in X_SQUARES:
        cr, cc = (0 if r == 1 else 7, 0 if c == 1 else 7)
        if board[r][c] == me:
            if board[cr][cc] == me:
                donation += 300
            else:
                donation -= int(x_pen_base * (0.55 if my_can_corner_now else 1.0))
        elif board[r][c] == opp:
            if board[cr][cc] == opp:
                donation -= 300
            else:
                donation += int(x_pen_base)

    for r, c in C_SQUARES:
        rel = []
        if r in (0, 7):
            rel.append((r, 0 if c < 4 else 7))
        if c in (0, 7):
            rel.append((0 if r < 4 else 7, c))

        if board[r][c] == me:
            has_anchor = any(board[x][y] == me for x, y in rel)
            if has_anchor:
                donation += 200
            else:
                donation -= int(c_pen_base * (0.70 if my_can_corner_now else 1.0))
        elif board[r][c] == opp:
            has_anchor = any(board[x][y] == opp for x, y in rel)
            if has_anchor:
                donation -= 200
            else:
                donation += int(c_pen_base)

    edge_shape = edge_shape_score(board, me)

    return corner + edge + stable + locked_corner + locked_full + edge_shape + donation + mobility + disc


def choose_depth(e):
    if e <= 10:
        return DEPTH_VERY_LATE
    if e <= 20:
        return DEPTH_LATE
    if e <= 30:
        return DEPTH_MID
    return DEPTH_EARLY


def move_order_key(board, move, to_play):
    t = tuple(move)

    if t in CORNERS:
        return (10, 0, 0)

    danger = 0
    if t in X_SQUARES:
        danger = 2
    elif t in C_SQUARES:
        danger = 1

    nb = execute(board, move, to_play)

    opp_corner = 1 if gives_opponent_corner(nb, -to_play) else 0

    mym = len(get_moves(nb, to_play))
    oppm = len(get_moves(nb, -to_play))
    mob = mym - oppm

    return (3 - 2 * opp_corner, mob, -danger)


def should_exact_solve(board, to_play):
    _, _, e = count_discs(board)
    if e > ENDGAME_SOLVE_EMPTY:
        return False

    moves = get_moves(board, to_play)
    if len(moves) >= ENDGAME_SOLVE_BRANCH_MAX:
        return False

    opp_moves = get_moves(board, -to_play)
    if len(moves) == 0 or len(opp_moves) == 0:
        return True

    if any(tuple(m) in CORNERS for m in moves):
        return True

    return False


def bump_node():
    global _node
    _node += 1
    return _node <= NODE_LIMIT


def exact_solve(board, to_play, me, alpha, beta, prev_pass=False):
    if not bump_node():
        return evaluate(board, me)

    k = (board_key(board), to_play, prev_pass)
    if k in _exact_tt:
        return _exact_tt[k]

    moves = get_moves(board, to_play)
    if not moves:
        if prev_pass:
            sc = final_diff(board, me) * 1000000
            _exact_tt[k] = sc
            return sc
        sc = exact_solve(board, -to_play, me, alpha, beta, True)
        sc += PASS_BONUS if to_play != me else -PASS_BONUS
        _exact_tt[k] = sc
        return sc

    ordered = sorted(moves, key=lambda m: move_order_key(board, m, to_play), reverse=True)

    if to_play == me:
        best = -10**18
        for m in ordered:
            nb = execute(board, m, to_play)
            sc = exact_solve(nb, -to_play, me, alpha, beta, False)

            if len(get_moves(nb, -to_play)) == 0:
                sc += PASS_BONUS

            best = max(best, sc)
            alpha = max(alpha, best)
            if alpha >= beta:
                break
    else:
        best = 10**18
        for m in ordered:
            nb = execute(board, m, to_play)
            sc = exact_solve(nb, -to_play, me, alpha, beta, False)

            if len(get_moves(nb, -to_play)) == 0:
                sc -= PASS_BONUS

            best = min(best, sc)
            beta = min(beta, best)
            if alpha >= beta:
                break

    _exact_tt[k] = best
    return best


def qsearch(board, to_play, me, alpha, beta, depth_q):
    if not bump_node():
        return evaluate(board, me)

    stand = evaluate(board, me)
    if depth_q <= 0:
        return stand

    if to_play == me:
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
    else:
        if stand <= alpha:
            return stand
        beta = min(beta, stand)

    moves = get_moves(board, to_play)
    if not moves:
        if len(get_moves(board, -to_play)) == 0:
            return final_diff(board, me) * 1000000
        base = evaluate(board, me)
        base += PASS_BONUS if to_play != me else -PASS_BONUS
        return base

    tactical = []
    for m in moves:
        t = tuple(m)
        if t in CORNERS or t in X_SQUARES or t in C_SQUARES:
            tactical.append(m)
            continue
        nb = execute(board, m, to_play)
        if gives_opponent_corner(nb, -to_play):
            tactical.append(m)

    if not tactical:
        return stand

    tactical = sorted(tactical, key=lambda m: move_order_key(board, m, to_play), reverse=True)

    if to_play == me:
        best = stand
        for m in tactical:
            nb = execute(board, m, to_play)
            sc = qsearch(nb, -to_play, me, alpha, beta, depth_q - 1)
            best = max(best, sc)
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best
    else:
        best = stand
        for m in tactical:
            nb = execute(board, m, to_play)
            sc = qsearch(nb, -to_play, me, alpha, beta, depth_q - 1)
            best = min(best, sc)
            beta = min(beta, best)
            if alpha >= beta:
                break
        return best


def negamax(board, to_play, me, depth, alpha, beta, prev_pass=False):
    if not bump_node():
        return evaluate(board, me)

    k = (board_key(board), to_play, depth, prev_pass)
    if k in _tt:
        return _tt[k]

    moves = get_moves(board, to_play)
    if not moves:
        if prev_pass:
            sc = final_diff(board, me) * 1000000
            _tt[k] = sc
            return sc
        sc = negamax(board, -to_play, me, depth - 1, alpha, beta, True)
        sc += PASS_BONUS if to_play != me else -PASS_BONUS
        _tt[k] = sc
        return sc

    if should_exact_solve(board, to_play):
        sc = exact_solve(board, to_play, me, alpha, beta, prev_pass)
        _tt[k] = sc
        return sc

    if depth <= 0:
        sc = qsearch(board, to_play, me, alpha, beta, Q_DEPTH)
        _tt[k] = sc
        return sc

    ordered = sorted(moves, key=lambda m: move_order_key(board, m, to_play), reverse=True)

    if to_play == me:
        best = -10**18
        for m in ordered:
            nb = execute(board, m, to_play)
            sc = negamax(nb, -to_play, me, depth - 1, alpha, beta, False)

            if len(get_moves(nb, -to_play)) == 0:
                sc += PASS_BONUS

            best = max(best, sc)
            alpha = max(alpha, best)
            if alpha >= beta:
                break
    else:
        best = 10**18
        for m in ordered:
            nb = execute(board, m, to_play)
            sc = negamax(nb, -to_play, me, depth - 1, alpha, beta, False)

            if len(get_moves(nb, -to_play)) == 0:
                sc -= PASS_BONUS

            best = min(best, sc)
            beta = min(beta, best)
            if alpha >= beta:
                break

    _tt[k] = best
    return best


def choose_move(board, moves, me):
    for m in moves:
        if tuple(m) in CORNERS:
            return m

    _, _, e = count_discs(board)
    depth = choose_depth(e)

    ordered = sorted(moves, key=lambda m: move_order_key(board, m, me), reverse=True)

    best = None
    best_sc = -10**18

    for m in ordered:
        nb = execute(board, m, me)
        sc = negamax(nb, -me, me, depth - 1, -10**18, 10**18, False)

        if gives_opponent_corner(nb, -me):
            sc -= 3500

        if sc > best_sc:
            best_sc = sc
            best = m

    return best if best is not None else moves[0]


def getAction(board, moves):
    global _node

    if STAT_ENABLE:
        _stat["t0"] = time.perf_counter()
        _stat["getMoves"] = 0
        _stat["getMoves_hit"] = 0
        _stat["execute"] = 0
        _stat["execute_hit"] = 0

    if detect_new_game(board):
        _tt.clear()
        _exact_tt.clear()
        if CACHE_ENABLE:
            _moves_cache.clear()
            _exec_cache.clear()

        if hasattr(getAction, "prev_board"):
            getAction.prev_board = None
        if hasattr(getAction, "opp_xc_total"):
            getAction.opp_xc_total = 0
            getAction.opp_xc_hits = 0
        if hasattr(getAction, "initialized"):
            getAction.initialized = False

    if not hasattr(getAction, "initialized") or not getAction.initialized:
        getAction.initialized = True
        getAction.my_color = infer_my_color(board)
        getAction.prev_board = None
        getAction.opp_xc_total = 0
        getAction.opp_xc_hits = 0

    me = getAction.my_color

    if OBS_ENABLE:
        mv = detect_opp_placed(getAction.prev_board, board, me)
        if mv is not None:
            getAction.opp_xc_total = min(OBS_MAX, getAction.opp_xc_total + 1)
            if mv in X_SQUARES or mv in C_SQUARES:
                getAction.opp_xc_hits = min(OBS_MAX, getAction.opp_xc_hits + 1)

    if is_terminal(board) or not moves:
        getAction.prev_board = fast_copy(board)
        if STAT_ENABLE:
            dt = (time.perf_counter() - _stat["t0"]) * 1000.0
            _stat["time_ms"] = dt
            _stat["nodes"] = _node
            hit = (_stat["getMoves_hit"] / _stat["getMoves"]) if _stat["getMoves"] else 0.0
            ehit = (_stat["execute_hit"] / _stat["execute"]) if _stat["execute"] else 0.0
            print(f"[AI] time={dt:.2f}ms nodes={_node} getMoves={_stat['getMoves']} hit={hit:.1%} execute={_stat['execute']} ehit={ehit:.1%}")
        return [0, 0]

    _node = 0

    chosen = choose_move(board, moves, me)

    getAction.prev_board = fast_copy(board)

    if STAT_ENABLE:
        dt = (time.perf_counter() - _stat["t0"]) * 1000.0
        _stat["time_ms"] = dt
        _stat["nodes"] = _node
        hit = (_stat["getMoves_hit"] / _stat["getMoves"]) if _stat["getMoves"] else 0.0
        ehit = (_stat["execute_hit"] / _stat["execute"]) if _stat["execute"] else 0.0
        print(f"[AI] time={dt:.2f}ms nodes={_node} getMoves={_stat['getMoves']} hit={hit:.1%} execute={_stat['execute']} ehit={ehit:.1%}")

    return chosen