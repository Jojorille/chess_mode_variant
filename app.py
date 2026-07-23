import json, uuid, random, copy
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

PIECES_SCORE = {'p': 1, 'n': 3, 'b': 3, 'r': 5, 'q': 9, 'k': 0}

class ChessEngine:
    @staticmethod
    def get_piece_moves(board, r, c, turn, variant, hidden_queen, en_passant_target=None):
        piece = board[r][c]
        piece_lower = piece.lower()
        moves = []
        directions = []
        max_steps = 1
        
        is_hidden_queen = False
        if hidden_queen and hidden_queen.get(turn) == [r, c]:
            is_hidden_queen = True

        if piece_lower == 'p' or is_hidden_queen:
            dr = -1 if turn == 'white' else 1
            start_row = 6 if turn == 'white' else 1
            
            # Mouvement standard pion
            if 0 <= r + dr < 8 and board[r + dr][c] == '':
                m = {'from': [r, c], 'to': [r + dr, c], 'is_capture': False, 'is_ep': False, 'hq_reveal': False}
                moves.append(m)
                if r == start_row and board[r + 2*dr][c] == '':
                    m2 = {'from': [r, c], 'to': [r + 2*dr, c], 'is_capture': False, 'is_ep': False, 'hq_reveal': False}
                    moves.append(m2)
            
            # Captures standard & En Passant
            for dc in [-1, 1]:
                if 0 <= r + dr < 8 and 0 <= c + dc < 8:
                    target = board[r + dr][c + dc]
                    is_enemy = (target and ((turn == 'white' and target.islower()) or (turn == 'black' and target.isupper())))
                    
                    if is_enemy:
                        moves.append({'from': [r, c], 'to': [r + dr, c + dc], 'is_capture': True, 'is_ep': False, 'hq_reveal': False})
                    elif en_passant_target == [r + dr, c + dc]:
                        moves.append({'from': [r, c], 'to': [r + dr, c + dc], 'is_capture': True, 'is_ep': True, 'hq_reveal': False})
                        
            if not is_hidden_queen:
                return moves
            
            # Si c'est la Dame Cachée, on ajoute les coups de Reine (qui la révéleront)
            directions = [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]
            max_steps = 8
            
        if piece_lower == 'n':
            directions = [(-2,-1), (-2,1), (-1,-2), (-1,2), (1,-2), (1,2), (2,-1), (2,1)]
        elif piece_lower == 'b':
            directions = [(-1,-1), (-1,1), (1,-1), (1,1)]
            max_steps = 8
        elif piece_lower == 'r':
            directions = [(-1,0), (1,0), (0,-1), (0,1)]
            max_steps = 8
        elif piece_lower == 'q' and not is_hidden_queen:
            directions = [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]
            max_steps = 8
        elif piece_lower == 'k':
            directions = [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]

        for dr, dc in directions:
            for step in range(1, max_steps + 1):
                nr, nc = r + dr * step, c + dc * step
                if 0 <= nr < 8 and 0 <= nc < 8:
                    target = board[nr][nc]
                    if target == '':
                        m = {'from': [r, c], 'to': [nr, nc], 'is_capture': False, 'is_ep': False}
                        if is_hidden_queen: m['hq_reveal'] = True
                        moves.append(m)
                    else:
                        if (turn == 'white' and target.islower()) or (turn == 'black' and target.isupper()):
                            m = {'from': [r, c], 'to': [nr, nc], 'is_capture': True, 'is_ep': False}
                            if is_hidden_queen: m['hq_reveal'] = True
                            moves.append(m)
                        break
                else:
                    break
        return moves

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
                            if p_type.lower() == 'p' and (r == 0 or r == 7): continue
                            moves.append({'from': 'drop', 'to': [r, c], 'piece': p_type, 'is_capture': False, 'is_ep': False})
                            
        if variant == 'antichess':
            captures = [m for m in moves if m.get('is_capture')]
            if captures: moves = captures
            
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
                    temp_board[sr][tc] = '' # Remove captured pawn
                
            if variant not in ['fog', 'antichess']:
                if not ChessEngine.is_in_check(temp_board, turn):
                    legal_moves.append(m)
            else:
                legal_moves.append(m)
                
        return legal_moves

    @staticmethod
    def is_in_check(board, turn):
        kr, kc = -1, -1
        king_char = 'K' if turn == 'white' else 'k'
        for r in range(8):
            for c in range(8):
                if board[r][c] == king_char:
                    kr, kc = r, c
                    break
        if kr == -1: return False
        
        opp = 'black' if turn == 'white' else 'white'
        for r in range(8):
            for c in range(8):
                p = board[r][c]
                if p and ((opp == 'white' and p.isupper()) or (opp == 'black' and p.islower())):
                    opp_moves = ChessEngine.get_piece_moves(board, r, c, opp, 'classic', {})
                    for m in opp_moves:
                        if m['to'] == [kr, kc]:
                            return True
        return False
        
    @staticmethod
    def calculate_vision(board, color, hidden_queen):
        vision = [[False]*8 for _ in range(8)]
        for r in range(8):
            for c in range(8):
                p = board[r][c]
                if p and ((color == 'white' and p.isupper()) or (color == 'black' and p.islower())):
                    vision[r][c] = True
                    moves = ChessEngine.get_piece_moves(board, r, c, color, 'fog', hidden_queen)
                    for m in moves:
                        vision[m['to'][0]][m['to'][1]] = True
                        
                    # Un pion voit ses 2 diagonales avant et les cases devant lui (jusqu'à être bloqué)
                    if p.lower() == 'p':
                        dr = -1 if color == 'white' else 1
                        for dc in [-1, 1]:
                            if 0 <= r + dr < 8 and 0 <= c + dc < 8:
                                vision[r + dr][c + dc] = True
                        
                        # Vision frontale (case bloquante incluse)
                        if 0 <= r + dr < 8:
                            vision[r + dr][c] = True
                            start_row = 6 if color == 'white' else 1
                            if r == start_row and board[r + dr][c] == '':
                                vision[r + 2*dr][c] = True
        return vision

class GameRoom:
    def __init__(self, room_id, variant):
        self.room_id = room_id
        self.variant = variant
        self.players = {} 
        self.turn = 'white'
        self.pockets = {'white': [], 'black': []}
        self.history = []
        self.en_passant_target = None
        
        self.hidden_queen = {'white': None, 'black': None}
        self.hidden_queen_revealed = {'white': False, 'black': False}
        self.bataille_ready = {'white': False, 'black': False} if variant == 'bataille' else None
        self.bataille_bench = {'white': ['R','N','B','Q','K','B','N','R','P','P','P','P','P','P','P','P'], 'black': ['r','n','b','q','k','b','n','r','p','p','p','p','p','p','p','p']}
        
        self.promotion_pending = None # Stores move info waiting for promotion choice
        
        self.board = self.init_board(variant)
        self.legal_moves = {}
        self.status = "playing"
        self.winner = None

    def init_board(self, variant):
        empty_row = [''] * 8
        if variant == 'bataille':
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
        
    def update_legal_moves(self):
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
                elif not moves:
                    w_score = sum(PIECES_SCORE.get(p.lower(), 0) for row in self.board for p in row if p and p.isupper())
                    b_score = sum(PIECES_SCORE.get(p.lower(), 0) for row in self.board for p in row if p and p.islower())
                    self.status = "game_over"
                    self.winner = 'white' if b_score > w_score else ('black' if w_score > b_score else 'draw')
            else:
                if not moves:
                    if self.variant != 'fog' and ChessEngine.is_in_check(self.board, self.turn):
                        self.status = "game_over"
                        self.winner = 'black' if self.turn == 'white' else 'white'
                    else:
                        self.status = "game_over"
                        self.winner = 'draw'

rooms = {}

@app.websocket("/ws/{room_id}/{player_color}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_color: str):
    await websocket.accept()
    if room_id not in rooms:
        rooms[room_id] = GameRoom(room_id, 'classic')
    room = rooms[room_id]
    room.players[player_color] = websocket
    
    room.update_legal_moves()
    await broadcast_state(room)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message['type'] == 'move':
                if room.turn == player_color and room.status == "playing":
                    m = message['move']
                    
                    if m['from'] == 'drop':
                        p_type = m['piece']
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
                        if moving_piece.lower() == 'p' and (tr == 0 or tr == 7):
                            room.status = "awaiting_promotion"
                            room.promotion_pending = {'to': [tr, tc], 'color': player_color}
                        else:
                            room.turn = 'black' if room.turn == 'white' else 'white'
                            
                    room.update_legal_moves()
                    await broadcast_state(room)
                    
            elif message['type'] == 'promote':
                if room.status == "awaiting_promotion" and room.promotion_pending['color'] == player_color:
                    tr, tc = room.promotion_pending['to']
                    chosen = message['piece']
                    room.board[tr][tc] = chosen.upper() if player_color == 'white' else chosen.lower()
                    room.status = "playing"
                    room.promotion_pending = None
                    room.turn = 'black' if room.turn == 'white' else 'white'
                    room.update_legal_moves()
                    await broadcast_state(room)
                    
            elif message['type'] == 'hidden_queen_setup':
                if room.variant == 'hidden_queen' and not room.hidden_queen[player_color]:
                    room.hidden_queen[player_color] = message['pos']
                    room.update_legal_moves()
                    await broadcast_state(room)
                    
            elif message['type'] == 'bataille_place':
                if room.variant == 'bataille' and not room.bataille_ready[player_color]:
                    room.board = message['board']
                    room.bataille_bench[player_color] = message['bench']
                    
            elif message['type'] == 'bataille_ready':
                if room.variant == 'bataille':
                    room.bataille_ready[player_color] = True
                    room.update_legal_moves()
                    await broadcast_state(room)

    except WebSocketDisconnect:
        room.players.pop(player_color, None)
        if not room.players:
            rooms.pop(room_id, None)

async def broadcast_state(room):
    for color, ws in room.players.items():
        try:
            board_to_send = copy.deepcopy(room.board)
            
            # Masking for Fog of War
            vision_map = None
            if room.variant == 'fog':
                vision_map = ChessEngine.calculate_vision(board_to_send, color, room.hidden_queen)
                for r in range(8):
                    for c in range(8):
                        if not vision_map[r][c]:
                            board_to_send[r][c] = ''
            
            # Hide unrevealed hidden queens
            if room.variant == 'hidden_queen':
                opp = 'black' if color == 'white' else 'white'
                if room.hidden_queen[opp] and not room.hidden_queen_revealed[opp]:
                    r, c = room.hidden_queen[opp]
                    if board_to_send[r][c].lower() == 'q':
                        board_to_send[r][c] = 'P' if opp == 'white' else 'p'

            state = {
                'type': 'state_update',
                'players_count': len(room.players),
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
                'hq_chosen': room.hidden_queen[color] is not None if room.variant == 'hidden_queen' else True
            }
                        
            await ws.send_text(json.dumps(state))
        except:
            pass

@app.post("/create_room")
async def create_room(variant: str = 'classic'):
    room_id = str(uuid.uuid4())[:8]
    rooms[room_id] = GameRoom(room_id, variant)
    return {"room_id": room_id}

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
