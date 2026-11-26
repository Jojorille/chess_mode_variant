import asyncio, json, uuid, random, copy, time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from clash_chess import ClashChessEngine, TICK_INTERVAL

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

PIECES_SCORE = {'p': 1, 'n': 3, 'b': 3, 'r': 5, 'q': 9, 'k': 3}

class ChessEngine:
    @staticmethod
    def get_piece_moves(board, r, c, turn, variant, hidden_queen, en_passant_target=None):
        piece = board[r][c]
        if not piece:
            return []
        
        # Verify piece belongs to active turn
        if turn == 'white' and not piece.isupper():
            return []
        if turn == 'black' and not piece.islower():
            return []

        piece_lower = piece.lower()
        moves = []
        
        is_hidden_queen = False
        if hidden_queen and hidden_queen.get(turn) == [r, c]:
            is_hidden_queen = True

        # Standard Pawn moves (when not acting as a hidden queen)
        if piece_lower == 'p' and not is_hidden_queen:
            dr = -1 if turn == 'white' else 1
            start_row = 6 if turn == 'white' else 1
            
            # Forward 1 square
            if 0 <= r + dr < 8 and board[r + dr][c] == '':
                moves.append({'from': [r, c], 'to': [r + dr, c], 'is_capture': False, 'is_ep': False, 'hq_reveal': False})
                # Forward 2 squares from start row (only if forward 1 is also empty)
                if r == start_row and 0 <= r + 2 * dr < 8 and board[r + 2 * dr][c] == '':
                    moves.append({'from': [r, c], 'to': [r + 2 * dr, c], 'is_capture': False, 'is_ep': False, 'hq_reveal': False})
            
            # Diagonal captures & En Passant
            for dc in [-1, 1]:
                if 0 <= r + dr < 8 and 0 <= c + dc < 8:
                    target = board[r + dr][c + dc]
                    is_enemy = (target and ((turn == 'white' and target.islower()) or (turn == 'black' and target.isupper())))
                    
                    if is_enemy:
                        moves.append({'from': [r, c], 'to': [r + dr, c + dc], 'is_capture': True, 'is_ep': False, 'hq_reveal': False})
                    elif en_passant_target == [r + dr, c + dc]:
                        moves.append({'from': [r, c], 'to': [r + dr, c + dc], 'is_capture': True, 'is_ep': True, 'hq_reveal': False})
                        
            return moves

        # Hidden Queen moves (moves like a Queen, but reveals ONLY if move is impossible for a pawn)
        if is_hidden_queen:
            dr_pawn = -1 if turn == 'white' else 1
            start_row = 6 if turn == 'white' else 1
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
            
            for dr, dc in directions:
                for step in range(1, 8):
                    nr, nc = r + dr * step, c + dc * step
                    if not (0 <= nr < 8 and 0 <= nc < 8):
                        break
                    target = board[nr][nc]
                    
                    # Blocked by friendly piece
                    if target != '' and ((turn == 'white' and target.isupper()) or (turn == 'black' and target.islower())):
                        break
                    
                    is_enemy = (target != '')
                    is_pawn_like = False
                    is_ep = False
                    
                    # Check if move mimics a natural legal pawn move
                    if dr == dr_pawn and dc == 0:
                        if step == 1 and not is_enemy:
                            is_pawn_like = True
                        elif step == 2 and r == start_row and not is_enemy and board[r + dr_pawn][c] == '':
                            is_pawn_like = True
                    elif dr == dr_pawn and abs(dc) == 1 and step == 1:
                        if is_enemy:
                            is_pawn_like = True
                        elif en_passant_target == [nr, nc]:
                            is_pawn_like = True
                            is_ep = True
                            is_enemy = True
                    
                    moves.append({
                        'from': [r, c],
                        'to': [nr, nc],
                        'is_capture': is_enemy,
                        'is_ep': is_ep,
                        'hq_reveal': not is_pawn_like
                    })
                    
                    if is_enemy:
                        break
            return moves

        # Standard pieces: Knight, Bishop, Rook, Queen, King
        directions = []
        max_steps = 1
        if piece_lower == 'n':
            directions = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
        elif piece_lower == 'b':
            directions = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
            max_steps = 7
        elif piece_lower == 'r':
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
            max_steps = 7
        elif piece_lower == 'q':
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
            max_steps = 7
        elif piece_lower == 'k':
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]

        for dr, dc in directions:
            for step in range(1, max_steps + 1):
                nr, nc = r + dr * step, c + dc * step
                if not (0 <= nr < 8 and 0 <= nc < 8):
                    break
                target = board[nr][nc]
                if target == '':
                    moves.append({'from': [r, c], 'to': [nr, nc], 'is_capture': False, 'is_ep': False})
                else:
                    if (turn == 'white' and target.islower()) or (turn == 'black' and target.isupper()):
                        moves.append({'from': [r, c], 'to': [nr, nc], 'is_capture': True, 'is_ep': False})
                    break
        return moves

    @staticmethod
    def is_in_check(board, turn, hidden_queen=None):
        kr, kc = -1, -1
        king_char = 'K' if turn == 'white' else 'k'
        for r in range(8):
            for c in range(8):
                if board[r][c] == king_char:
                    kr, kc = r, c
                    break
            if kr != -1:
                break
        if kr == -1:
            return False
        
        opp = 'black' if turn == 'white' else 'white'
        for r in range(8):
            for c in range(8):
                p = board[r][c]
                if p and ((opp == 'white' and p.isupper()) or (opp == 'black' and p.islower())):
                    opp_moves = ChessEngine.get_piece_moves(board, r, c, opp, 'classic', hidden_queen)
                    for m in opp_moves:
                        if m['to'] == [kr, kc]:
                            return True
        return False

    @staticmethod
    def get_legal_moves(board, turn, variant, pockets, hidden_queen, en_passant_target=None):
        moves = []
        for r in range(8):
            for c in range(8):
                p = board[r][c]
                if p and ((turn == 'white' and p.isupper()) or (turn == 'black' and p.islower())):
                    moves.extend(ChessEngine.get_piece_moves(board, r, c, turn, variant, hidden_queen, en_passant_target))
                    
        if variant == 'clubhouse':
            for r in range(8):
                for c in range(8):
                    if board[r][c] == '':
                        for p_type in set(pockets[turn]):
                            if p_type.lower() == 'p' and (r == 0 or r == 7):
                                continue
                            moves.append({'from': 'drop', 'to': [r, c], 'piece': p_type, 'is_capture': False, 'is_ep': False})
                            
        if variant == 'antichess':
            captures = [m for m in moves if m.get('is_capture')]
            if captures:
                moves = captures
            
        legal_moves = []
        for m in moves:
            temp_board = copy.deepcopy(board)
            if m['from'] == 'drop':
                temp_board[m['to'][0]][m['to'][1]] = m['piece']
            else:
                sr, sc = m['from']
                tr, tc = m['to']
                temp_board[tr][tc] = temp_board[sr][sc]
                temp_board[sr][sc] = ''
                if m.get('is_ep'):
                    temp_board[sr][tc] = ''
                
            if variant not in ['fog', 'antichess']:
                temp_hq = copy.deepcopy(hidden_queen)
                if temp_hq and temp_hq.get(turn) == [sr, sc]:
                    temp_hq[turn] = [tr, tc]
                if not ChessEngine.is_in_check(temp_board, turn, temp_hq):
                    legal_moves.append(m)
            else:
                legal_moves.append(m)
                
        return legal_moves

    @staticmethod
    def calculate_vision(board, color, hidden_queen=None, en_passant_target=None):
        vision = [[False] * 8 for _ in range(8)]
        for r in range(8):
            for c in range(8):
                p = board[r][c]
                if p and ((color == 'white' and p.isupper()) or (color == 'black' and p.islower())):
                    # 1. Squares occupied by the player's own pieces are always visible
                    vision[r][c] = True
                    # 3. Pawns always see their forward capture diagonals
                    if p.lower() == 'p':
                        dr = -1 if color == 'white' else 1
                        for dc in (-1, 1):
                            nr, nc = r + dr, c + dc
                            if 0 <= nr < 8 and 0 <= nc < 8:
                                vision[nr][nc] = True

        # 2. Exact legal move destinations for this player
        legal_moves = ChessEngine.get_legal_moves(
            board, color, 'fog', {'white': [], 'black': []}, hidden_queen, en_passant_target
        )
        for m in legal_moves:
            tr, tc = m['to']
            vision[tr][tc] = True

        return vision

class GameRoom:
    def __init__(self, room_id, variant, host_color='white'):
        self.room_id = room_id
        self.variant = variant
        self.host_color = host_color if host_color in ('white', 'black') else 'white'
        self.guest_color = 'black' if self.host_color == 'white' else 'white'
        self.players = {} 
        self.turn = 'white'
        self.pockets = {'white': [], 'black': []}
        self.history = []
        self.en_passant_target = None
        
        self.hidden_queen = {'white': None, 'black': None}
        self.hidden_queen_revealed = {'white': False, 'black': False}
        self.bataille_ready = {'white': False, 'black': False} if variant == 'bataille' else None
        self.bataille_bench = {'white': ['R','N','B','Q','K','B','N','R','P','P','P','P','P','P','P','P'], 'black': ['r','n','b','q','k','b','n','r','p','p','p','p','p','p','p','p']}
        
        self.promotion_pending = None
        self.clash_engine = ClashChessEngine() if variant == 'clash_chess' else None
        self.clash_task = None
        
        self.board = self.init_board(variant)
        self.legal_moves = {}
        self.status = "waiting" if variant == 'clash_chess' else "playing"
        self.winner = None

    def init_board(self, variant):
        empty_row = [''] * 8
        if variant in ('bataille', 'clash_chess'):
            return [empty_row.copy() for _ in range(8)]
            
        board = [
            ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'],
            ['p', 'p', 'p', 'p', 'p', 'p', 'p', 'p'],
            empty_row.copy(), empty_row.copy(), empty_row.copy(), empty_row.copy(),
            ['P', 'P', 'P', 'P', 'P', 'P', 'P', 'P'],
            ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        ]
        
        if variant == 'chess960':
            pieces = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
            while True:
                random.shuffle(pieces)
                r1 = pieces.index('R')
                r2 = len(pieces) - 1 - pieces[::-1].index('R')
                k = pieces.index('K')
                b1 = pieces.index('B')
                b2 = len(pieces) - 1 - pieces[::-1].index('B')
                if r1 < k < r2 and (b1 % 2) != (b2 % 2):
                    break
            board[7] = pieces.copy()
            board[0] = [p.lower() for p in pieces]
            
        return board

    def get_masked_board(self, color):
        """Return (board_copy, vision_map) with server-side anti-cheat masking applied."""
        board_to_send = copy.deepcopy(self.board)
        vision_map = None

        # Hide opponent deployment in Bataille Chess until both players confirm ready
        if self.variant == 'bataille' and not (
            self.bataille_ready['white'] and self.bataille_ready['black']
        ):
            opp_ranks = range(0, 4) if color == 'white' else range(4, 8)
            for r in opp_ranks:
                for c in range(8):
                    board_to_send[r][c] = ''

        # Masking for Fog of War
        if self.variant == 'fog':
            vision_map = ChessEngine.calculate_vision(
                self.board, color, self.hidden_queen, self.en_passant_target
            )
            for r in range(8):
                for c in range(8):
                    if not vision_map[r][c]:
                        board_to_send[r][c] = ''

        # Hide unrevealed hidden queens from the opponent
        if self.variant == 'hidden_queen':
            opp = 'black' if color == 'white' else 'white'
            if self.hidden_queen[opp] and not self.hidden_queen_revealed[opp]:
                r, c = self.hidden_queen[opp]
                if board_to_send[r][c].lower() == 'q':
                    board_to_send[r][c] = 'P' if opp == 'white' else 'p'

        return board_to_send, vision_map
        
    def update_legal_moves(self):
        if self.variant == 'clash_chess':
            self.legal_moves = {}
            return

        if self.status not in ["playing", "awaiting_promotion"]: 
            self.legal_moves = {}
            return
            
        if self.variant == 'hidden_queen':
            if not self.hidden_queen['white'] or not self.hidden_queen['black']:
                self.legal_moves = {}
                return
                
        if self.variant == 'bataille' and not (self.bataille_ready['white'] and self.bataille_ready['black']):
            self.legal_moves = {}
            return
            
        moves = ChessEngine.get_legal_moves(self.board, self.turn, self.variant, self.pockets, self.hidden_queen, self.en_passant_target)
        formatted = {}
        for m in moves:
            if m['from'] == 'drop':
                key = f"drop_{m['piece']}"
            else:
                key = f"{m['from'][0]},{m['from'][1]}"
            if key not in formatted:
                formatted[key] = []
            formatted[key].append(m)
        self.legal_moves = formatted
        
        if self.status == "playing":
            if self.variant == 'antichess':
                w_count = sum(1 for row in self.board for p in row if p and p.isupper())
                b_count = sum(1 for row in self.board for p in row if p and p.islower())
                
                if w_count == 0 or b_count == 0:
                    self.status = "game_over"
                    self.winner = 'white' if w_count == 0 else 'black'
                    self.legal_moves = {}
                elif not moves:
                    w_score = sum(PIECES_SCORE.get(p.lower(), 0) for row in self.board for p in row if p and p.isupper())
                    b_score = sum(PIECES_SCORE.get(p.lower(), 0) for row in self.board for p in row if p and p.islower())
                    self.status = "game_over"
                    self.winner = 'white' if b_score > w_score else ('black' if w_score > b_score else 'draw')
                    self.legal_moves = {}
            else:
                has_white_king = any(p == 'K' for row in self.board for p in row)
                has_black_king = any(p == 'k' for row in self.board for p in row)
                if not has_white_king:
                    self.status = "game_over"
                    self.winner = 'black'
                    self.legal_moves = {}
                elif not has_black_king:
                    self.status = "game_over"
                    self.winner = 'white'
                    self.legal_moves = {}
                elif not moves:
                    if self.variant != 'fog' and ChessEngine.is_in_check(self.board, self.turn, self.hidden_queen):
                        self.status = "game_over"
                        self.winner = 'black' if self.turn == 'white' else 'white'
                    else:
                        self.status = "game_over"
                        self.winner = 'draw'
                    self.legal_moves = {}

rooms = {}


async def run_clash_loop(room: GameRoom):
    """Server-authoritative real-time tick loop (>= 30 ticks/sec) for Clash Chess."""
    loop_interval = min(TICK_INTERVAL, 1.0 / 35.0)
    last_time = time.monotonic()
    next_tick_at = last_time
    try:
        while room.clash_engine and room.clash_engine.status == 'playing':
            next_tick_at += loop_interval
            sleep_dur = next_tick_at - time.monotonic()
            if sleep_dur > 0.0:
                await asyncio.sleep(sleep_dur * 0.75)
            elif sleep_dur < -0.2:
                next_tick_at = time.monotonic()
            else:
                await asyncio.sleep(0)

            if not room.clash_engine or room.clash_engine.status != 'playing':
                break

            now = time.monotonic()
            dt = min(max(now - last_time, 0.0), 0.1)
            last_time = now

            room.clash_engine.tick(dt)
            room.status = room.clash_engine.status
            room.winner = room.clash_engine.winner
            await broadcast_state(room)
    except asyncio.CancelledError:
        pass
    finally:
        if room.clash_task is asyncio.current_task():
            room.clash_task = None


@app.websocket("/ws/{room_id}/{player_color}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_color: str):
    await websocket.accept()
    if room_id not in rooms:
        rooms[room_id] = GameRoom(room_id, 'classic')
    room = rooms[room_id]

    if player_color in ('guest', 'auto'):
        player_color = room.guest_color
    elif player_color not in ('white', 'black'):
        player_color = 'black' if 'white' in room.players else 'white'

    room.players[player_color] = websocket

    if room.variant == 'clash_chess' and room.clash_engine:
        if (
            'white' in room.players
            and 'black' in room.players
            and not room.clash_engine.started
            and room.clash_engine.status != 'game_over'
        ):
            room.clash_engine.start()
            room.status = room.clash_engine.status
            if room.clash_task is None or room.clash_task.done():
                room.clash_task = asyncio.create_task(run_clash_loop(room))

    room.update_legal_moves()
    await broadcast_state(room)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except Exception:
                continue
            if not isinstance(message, dict):
                continue
            
            msg_type = message.get('type')

            if room.variant == 'clash_chess' and room.clash_engine:
                if msg_type == 'clash_spawn':
                    piece_type = message.get('piece')
                    try:
                        row = int(message.get('row'))
                        col = int(message.get('col'))
                    except (TypeError, ValueError):
                        continue
                    if isinstance(piece_type, str) and room.clash_engine.spawn_piece(
                        player_color, piece_type, row, col
                    ):
                        await broadcast_state(room)
                elif msg_type == 'clash_move':
                    piece_id = message.get('piece_id')
                    to_pos = message.get('to')
                    if (
                        isinstance(piece_id, str)
                        and isinstance(to_pos, list)
                        and len(to_pos) == 2
                    ):
                        try:
                            tr = int(to_pos[0])
                            tc = int(to_pos[1])
                        except (TypeError, ValueError):
                            continue
                        if room.clash_engine.move_piece(player_color, piece_id, tr, tc):
                            await broadcast_state(room)
                elif msg_type == 'clash_promote':
                    piece_id = message.get('piece_id')
                    chosen = message.get('piece')
                    if isinstance(piece_id, str) and isinstance(chosen, str):
                        if room.clash_engine.promote_piece(player_color, piece_id, chosen):
                            await broadcast_state(room)
                elif msg_type == 'resign':
                    if room.clash_engine.status != 'game_over':
                        room.clash_engine.resign(player_color)
                        room.status = room.clash_engine.status
                        room.winner = room.clash_engine.winner
                        if room.clash_task and not room.clash_task.done():
                            room.clash_task.cancel()
                        await broadcast_state(room)
                continue
            
            if msg_type == 'move':
                if room.turn == player_color and room.status == "playing":
                    m_in = message.get('move', {})
                    if not isinstance(m_in, dict):
                        continue
                    
                    # Server authoritative validation
                    key = f"drop_{m_in.get('piece')}" if m_in.get('from') == 'drop' else f"{m_in.get('from', [-1,-1])[0]},{m_in.get('from', [-1,-1])[1]}"
                    valid_move = None
                    if key in room.legal_moves:
                        for cand in room.legal_moves[key]:
                            if cand['to'] == m_in.get('to'):
                                if m_in.get('from') == 'drop':
                                    if cand.get('piece') == m_in.get('piece'):
                                        valid_move = cand
                                        break
                                else:
                                    valid_move = cand
                                    break
                    
                    if not valid_move:
                        # Reject illegal move cleanly without crashing
                        await broadcast_state(room)
                        continue
                    
                    m = valid_move
                    
                    if m['from'] == 'drop':
                        p_type = m['piece']
                        if p_type in room.pockets[player_color]:
                            room.board[m['to'][0]][m['to'][1]] = p_type
                            room.pockets[player_color].remove(p_type)
                            room.en_passant_target = None
                            room.turn = 'black' if room.turn == 'white' else 'white'
                    else:
                        sr, sc = m['from']
                        tr, tc = m['to']
                        moving_piece = room.board[sr][sc]
                        target_piece = room.board[tr][tc]
                        
                        # Handle capture
                        if target_piece:
                            room.pockets[player_color].append(target_piece.upper() if player_color == 'white' else target_piece.lower())
                            if target_piece.lower() == 'k' and room.variant != 'antichess':
                                room.status = "game_over"
                                room.winner = player_color
                        elif m.get('is_ep'):
                            ep_piece = room.board[sr][tc]
                            room.pockets[player_color].append(ep_piece.upper() if player_color == 'white' else ep_piece.lower())
                            room.board[sr][tc] = ''
                                
                        room.board[tr][tc] = moving_piece
                        room.board[sr][sc] = ''
                        
                        # En Passant logic setup
                        if moving_piece.lower() == 'p' and abs(tr - sr) == 2:
                            room.en_passant_target = [(sr + tr) // 2, sc]
                        else:
                            room.en_passant_target = None
                        
                        # Hidden queen logic
                        if room.variant == 'hidden_queen':
                            if room.hidden_queen[player_color] == [sr, sc]:
                                room.hidden_queen[player_color] = [tr, tc]
                                if m.get('hq_reveal'):
                                    room.hidden_queen_revealed[player_color] = True
                                    room.board[tr][tc] = 'Q' if player_color == 'white' else 'q'
                        
                        # Promotion intercept
                        if room.status != "game_over" and moving_piece.lower() == 'p' and (tr == 0 or tr == 7):
                            room.status = "awaiting_promotion"
                            room.promotion_pending = {'to': [tr, tc], 'color': player_color}
                        else:
                            if room.status != "game_over":
                                room.turn = 'black' if room.turn == 'white' else 'white'
                            
                    room.update_legal_moves()
                    await broadcast_state(room)
                    
            elif msg_type == 'promote':
                if room.status == "awaiting_promotion" and room.promotion_pending and room.promotion_pending['color'] == player_color:
                    tr, tc = room.promotion_pending['to']
                    chosen = message.get('piece', 'Q')
                    if chosen.upper() not in ['Q', 'R', 'B', 'N']:
                        chosen = 'Q'
                    room.board[tr][tc] = chosen.upper() if player_color == 'white' else chosen.lower()
                    room.status = "playing"
                    room.promotion_pending = None
                    room.turn = 'black' if room.turn == 'white' else 'white'
                    room.update_legal_moves()
                    await broadcast_state(room)
                    
            elif msg_type == 'hidden_queen_setup':
                if room.variant == 'hidden_queen' and not room.hidden_queen[player_color]:
                    pos = message.get('pos')
                    if isinstance(pos, list) and len(pos) == 2:
                        r, c = pos
                        if 0 <= r < 8 and 0 <= c < 8:
                            piece = room.board[r][c]
                            is_own_pawn = (piece == 'P' if player_color == 'white' else piece == 'p')
                            if is_own_pawn:
                                room.hidden_queen[player_color] = [r, c]
                                room.update_legal_moves()
                                await broadcast_state(room)
                    
            elif msg_type == 'bataille_place':
                if room.variant == 'bataille' and not room.bataille_ready[player_color]:
                    allowed_ranks = [4, 5, 6, 7] if player_color == 'white' else [0, 1, 2, 3]
                    new_board = message.get('board')
                    new_bench = message.get('bench')
                    if isinstance(new_board, list) and len(new_board) == 8 and isinstance(new_bench, list):
                        for r in allowed_ranks:
                            if isinstance(new_board[r], list) and len(new_board[r]) == 8:
                                for c in range(8):
                                    val = new_board[r][c]
                                    if val == '' or (player_color == 'white' and val.isupper()) or (player_color == 'black' and val.islower()):
                                        room.board[r][c] = val
                        room.bataille_bench[player_color] = [p for p in new_bench if (player_color == 'white' and p.isupper()) or (player_color == 'black' and p.islower())]
                        await broadcast_state(room)
                    
            elif msg_type == 'bataille_ready':
                if room.variant == 'bataille' and not room.bataille_ready[player_color]:
                    if len(room.bataille_bench[player_color]) == 0:
                        king_char = 'K' if player_color == 'white' else 'k'
                        allowed_ranks = range(4, 8) if player_color == 'white' else range(0, 4)
                        has_king = any(room.board[r][c] == king_char for r in allowed_ranks for c in range(8))
                        if has_king:
                            room.bataille_ready[player_color] = True
                            room.update_legal_moves()
                            await broadcast_state(room)

            elif msg_type == 'resign':
                if room.status in ["playing", "awaiting_promotion"]:
                    room.status = "game_over"
                    room.winner = 'black' if player_color == 'white' else 'white'
                    room.legal_moves = {}
                    await broadcast_state(room)

    except WebSocketDisconnect:
        if room.players.get(player_color) == websocket:
            room.players.pop(player_color, None)

async def broadcast_state(room):
    if room.variant == 'clash_chess' and room.clash_engine:
        for color, ws in list(room.players.items()):
            try:
                state = {
                    'type': 'state_update',
                    'players_count': len(room.players),
                    'assigned_color': color,
                    'variant': 'clash_chess',
                    'status': room.clash_engine.status,
                    'winner': room.clash_engine.winner,
                    'turn': None,
                    'clash': room.clash_engine.get_state_for_player(color),
                }
                await ws.send_text(json.dumps(state))
            except Exception:
                pass
        return

    for color, ws in list(room.players.items()):
        try:
            board_to_send, vision_map = room.get_masked_board(color)

            state = {
                'type': 'state_update',
                'players_count': len(room.players),
                'assigned_color': color,
                'board': board_to_send,
                'vision_map': vision_map,
                'turn': room.turn,
                'variant': room.variant,
                'pockets': room.pockets,
                'bataille_ready': room.bataille_ready,
                'bataille_bench': room.bataille_bench[color] if room.variant == 'bataille' else [],
                'legal_moves': room.legal_moves if room.turn == color else {},
                'status': room.status,
                'winner': room.winner,
                'hq_chosen': room.hidden_queen[color] is not None if room.variant == 'hidden_queen' else True,
                'my_hidden_queen': room.hidden_queen[color] if room.variant == 'hidden_queen' else None
            }
                        
            await ws.send_text(json.dumps(state))
        except Exception:
            pass

@app.post("/create_room")
async def create_room(variant: str = 'classic', color: str = 'random'):
    room_id = str(uuid.uuid4())[:8]
    if color in ('white', 'black'):
        host_color = color
    else:
        host_color = random.choice(['white', 'black'])
    rooms[room_id] = GameRoom(room_id, variant, host_color=host_color)
    return {
        "room_id": room_id,
        "host_color": host_color,
        "guest_color": rooms[room_id].guest_color,
    }

@app.get("/room_info/{room_id}")
async def get_room_info(room_id: str):
    room = rooms.get(room_id)
    if not room:
        return {"exists": False}
    return {
        "exists": True,
        "variant": room.variant,
        "host_color": room.host_color,
        "guest_color": room.guest_color,
    }

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
