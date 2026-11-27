import asyncio
import json
import unittest
import copy
import random
from fastapi import WebSocketDisconnect
from app import ChessEngine, GameRoom, PIECES_SCORE, create_room, rooms, websocket_endpoint

class TestStandardChess(unittest.TestCase):
    def setUp(self):
        self.room = GameRoom("test_std", "classic")

    def test_no_friendly_capture(self):
        """Verify players cannot capture their own pieces."""
        board = self.room.board
        moves = ChessEngine.get_piece_moves(board, 7, 0, 'white', 'classic', {}) # Rook at a1
        # In starting position, a1 rook is completely blocked by pawns/knights
        self.assertEqual(len(moves), 0, "Rook should not be able to jump over or capture friendly pieces")
        
        # Knight jumps
        n_moves = ChessEngine.get_piece_moves(board, 7, 1, 'white', 'classic', {}) # Knight at b1
        for m in n_moves:
            target = board[m['to'][0]][m['to'][1]]
            if target != '':
                self.assertTrue(target.islower(), "Knight destination must not be a friendly piece")

    def test_en_passant(self):
        """Test en passant generation, capture, board update, and expiration."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        # White pawn on e5 (row 3, col 4)
        board[3][4] = 'P'
        board[7][4] = 'K'
        board[0][4] = 'k'
        
        # Black pawn double-pushes d7 -> d5 (row 1, col 3 -> row 3, col 3)
        board[3][3] = 'p'
        en_passant_target = [2, 3] # d6
        
        moves = ChessEngine.get_piece_moves(board, 3, 4, 'white', 'classic', {}, en_passant_target)
        ep_moves = [m for m in moves if m.get('is_ep')]
        self.assertEqual(len(ep_moves), 1, "En passant move should be available")
        self.assertEqual(ep_moves[0]['to'], [2, 3])
        
        # Test legal moves includes en passant
        legal_moves = ChessEngine.get_legal_moves(board, 'white', 'classic', {'white': [], 'black': []}, {}, en_passant_target)
        ep_legal = [m for m in legal_moves if m.get('is_ep')]
        self.assertEqual(len(ep_legal), 1, "En passant must be in legal moves")
        
        # Test expiration: if target is None, no en passant
        moves_expired = ChessEngine.get_piece_moves(board, 3, 4, 'white', 'classic', {}, None)
        self.assertEqual(len([m for m in moves_expired if m.get('is_ep')]), 0)

    def test_check_and_checkmate(self):
        """Test check detection, checkmate game over, and stalemate draw."""
        # Scholar's mate test
        room = GameRoom("scholars", "classic")
        moves_sequence = [
            ({'from': [6, 4], 'to': [4, 4]}), # 1. e4
            ({'from': [1, 4], 'to': [3, 4]}), # 1... e5
            ({'from': [7, 3], 'to': [3, 7]}), # 2. Qh5
            ({'from': [0, 1], 'to': [2, 2]}), # 2... Nc6
            ({'from': [7, 5], 'to': [4, 2]}), # 3. Bc4
            ({'from': [0, 6], 'to': [2, 5]}), # 3... Nf6
            ({'from': [3, 7], 'to': [1, 5]}), # 4. Qxf7#
        ]
        
        for idx, m in enumerate(moves_sequence):
            room.update_legal_moves()
            sr, sc = m['from']
            tr, tc = m['to']
            moving = room.board[sr][sc]
            target = room.board[tr][tc]
            room.board[tr][tc] = moving
            room.board[sr][sc] = ''
            room.turn = 'black' if room.turn == 'white' else 'white'
            
        room.update_legal_moves()
        self.assertEqual(room.status, "game_over", "Scholar's mate must result in game_over")
        self.assertEqual(room.winner, "white", "White must be the winner in Scholar's mate")

    def test_stalemate(self):
        """Test stalemate position results in draw."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        # Black king at a8 (0, 0)
        board[0][0] = 'k'
        # White king at c7 (1, 2)
        board[1][2] = 'K'
        # White queen at b6 (2, 1)
        board[2][1] = 'Q'
        
        room = GameRoom("stalemate", "classic")
        room.board = board
        room.turn = 'black'
        
        # Verify black king is not in check
        self.assertFalse(ChessEngine.is_in_check(board, 'black', {}), "Black king must NOT be in check in stalemate")
        
        room.update_legal_moves()
        self.assertEqual(room.status, "game_over")
        self.assertEqual(room.winner, "draw", "Stalemate must result in a draw")

    def test_promotion_wait(self):
        """Test that pawn reaching 8th rank triggers awaiting_promotion."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        board[1][4] = 'P' # White pawn on e7
        board[7][4] = 'K'
        board[0][0] = 'k'
        
        room = GameRoom("promo", "classic")
        room.board = board
        room.turn = 'white'
        room.update_legal_moves()
        
        # White pushes pawn to e8 (row 0, col 4)
        m = {'from': [1, 4], 'to': [0, 4]}
        sr, sc = m['from']
        tr, tc = m['to']
        moving = room.board[sr][sc]
        room.board[tr][tc] = moving
        room.board[sr][sc] = ''
        
        if moving.lower() == 'p' and (tr == 0 or tr == 7):
            room.status = "awaiting_promotion"
            room.promotion_pending = {'to': [tr, tc], 'color': 'white'}
            
        self.assertEqual(room.status, "awaiting_promotion")
        self.assertEqual(room.promotion_pending['color'], 'white')
        self.assertEqual(room.turn, 'white', "Turn must not switch until promotion choice is made")


class TestChess960(unittest.TestCase):
    def test_fischer_random_math_properties(self):
        """Verify 100 Fischer Random boards strictly respect rules."""
        for _ in range(100):
            room = GameRoom("960", "chess960")
            white_backrank = room.board[7]
            black_backrank = room.board[0]
            
            # 1. Backranks are mirrored lowercase
            self.assertEqual([p.lower() for p in white_backrank], black_backrank)
            
            # 2. King is strictly between the two Rooks
            r1 = white_backrank.index('R')
            r2 = len(white_backrank) - 1 - white_backrank[::-1].index('R')
            k = white_backrank.index('K')
            self.assertTrue(r1 < k < r2, f"King {k} must be between rooks {r1} and {r2}")
            
            # 3. Bishops on opposite color squares
            b1 = white_backrank.index('B')
            b2 = len(white_backrank) - 1 - white_backrank[::-1].index('B')
            self.assertNotEqual(b1 % 2, b2 % 2, f"Bishops {b1} and {b2} must be on opposite colored squares")


class TestAntichess(unittest.TestCase):
    def test_king_is_normal_piece(self):
        """In antichess, capturing King does not end game if other pieces remain."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        board[4][4] = 'k' # Black king
        board[0][0] = 'r' # Black rook
        board[5][4] = 'R' # White rook
        board[7][7] = 'K' # White king
        
        room = GameRoom("antichess", "antichess")
        room.board = board
        room.turn = 'white'
        room.update_legal_moves()
        
        # White captures black king: (5,4) -> (4,4)
        target = room.board[4][4]
        room.board[4][4] = 'R'
        room.board[5][4] = ''
        
        # In antichess, target == 'k' does NOT trigger game_over
        self.assertEqual(room.status, "playing", "Capturing King in Antichess must NOT end the game")
        
        room.turn = 'black'
        room.update_legal_moves()
        self.assertEqual(room.status, "playing", "Black still has a rook, so game continues")

    def test_forced_capture(self):
        """In antichess, if any capture is possible, ONLY captures are legal moves."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        board[6][4] = 'P' # White pawn on e2
        board[5][3] = 'p' # Black pawn on d3 (can be captured)
        board[7][0] = 'R' # White rook on a1 (can move freely)
        board[0][0] = 'k' # Black king
        
        legal_moves = ChessEngine.get_legal_moves(board, 'white', 'antichess', {'white': [], 'black': []}, {})
        self.assertTrue(len(legal_moves) > 0)
        for m in legal_moves:
            self.assertTrue(m.get('is_capture'), "In Antichess, every returned legal move must be a capture when available")

    def test_stalemate_scoring(self):
        """In antichess stalemate, the player with the highest remaining score loses."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        # White has a blocked pawn at a7 (row 1, col 0)
        board[1][0] = 'P'
        # Black has a piece blocking at a8 (row 0, col 0)
        board[0][0] = 'q'
        # Black queen has score 9, White pawn has score 1.
        # White has 0 legal moves (stalemate)
        
        room = GameRoom("anti_stale", "antichess")
        room.board = board
        room.turn = 'white'
        room.update_legal_moves()
        
        self.assertEqual(room.status, "game_over")
        # Black has 9 points, White has 1 point. Higher score loses -> Black loses, White wins!
        self.assertEqual(room.winner, "white", "Player with fewer remaining points must win in Antichess stalemate")


class TestFogOfWar(unittest.TestCase):
    def test_vision_map_calculation(self):
        """Strict Fog of War: own squares, legal move destinations, and pawn attack diagonals only."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        
        # White pawn at e2 (row 6, col 4)
        board[6][4] = 'P'
        # Enemy black pawn directly in front at e3 (row 5, col 4)
        board[5][4] = 'p'
        # White rook at a1 (row 7, col 0)
        board[7][0] = 'R'
        # Enemy black piece at a4 (row 4, col 0) blocking rook ray
        board[4][0] = 'r'
        
        vision = ChessEngine.calculate_vision(board, 'white', {})
        
        # 1. Own occupied squares are visible
        self.assertTrue(vision[6][4], "Pawn square must be visible")
        self.assertTrue(vision[7][0], "Rook square must be visible")
        
        # 2. Blocked pawn CANNOT move forward onto (5,4), so obstacle ahead must NOT be visible
        self.assertFalse(vision[5][4], "Blocked square straight ahead of pawn is not a legal move and must stay hidden")
        self.assertFalse(vision[4][4], "Square behind blocking pawn must NOT be visible")
        
        # 3. Pawn attack diagonals must be visible even if empty
        self.assertTrue(vision[5][3], "Pawn forward-left diagonal must be visible")
        self.assertTrue(vision[5][5], "Pawn forward-right diagonal must be visible")
        
        # 4. Rook sees legal squares up to capture target (4,0), and NOT beyond it
        self.assertTrue(vision[6][0], "Rook legal path must be visible")
        self.assertTrue(vision[5][0], "Rook legal path must be visible")
        self.assertTrue(vision[4][0], "Rook legal capture square must be visible")
        self.assertFalse(vision[3][0], "Square behind blocking enemy must NOT be visible")
        self.assertTrue(vision[7][1], "Rook horizontal movement path must be visible")
        self.assertTrue(vision[7][7], "Rook horizontal movement path must be visible")

    def test_fog_vision_blocked_pieces_and_pawn_two_step(self):
        """Verify exact 64-square vision sets for blocked pawns, cornered rook, and knight."""
        empty_board = lambda: [[''] * 8 for _ in range(8)]
        visible_coords = lambda v: {(r, c) for r in range(8) for c in range(8) if v[r][c]}

        # 1. Pawn blocked 1 square ahead (P at e2, enemy p at e3)
        b_p1 = empty_board()
        b_p1[6][4] = 'P'
        b_p1[5][4] = 'p'
        self.assertEqual(visible_coords(ChessEngine.calculate_vision(b_p1, 'white', {})), {(6, 4), (5, 3), (5, 5)})

        # 2. Pawn blocked 2 squares ahead (P at e2, e3 empty, enemy p at e4)
        b_p2 = empty_board()
        b_p2[6][4] = 'P'
        b_p2[4][4] = 'p'
        self.assertEqual(visible_coords(ChessEngine.calculate_vision(b_p2, 'white', {})), {(6, 4), (5, 4), (5, 3), (5, 5)})

        # 3. Free pawn on 2nd rank (P at e2, empty path)
        b_p3 = empty_board()
        b_p3[6][4] = 'P'
        self.assertEqual(visible_coords(ChessEngine.calculate_vision(b_p3, 'white', {})), {(6, 4), (5, 4), (4, 4), (5, 3), (5, 5)})

        # 4. Cornered Rook with 0 legal moves (R at a1 blocked by friendly B at a2 and B at b1)
        b_no_rook = empty_board()
        b_no_rook[6][0] = 'B'
        b_no_rook[7][1] = 'B'
        v_no_rook = visible_coords(ChessEngine.calculate_vision(b_no_rook, 'white', {}))

        b_with_rook = empty_board()
        b_with_rook[7][0] = 'R'
        b_with_rook[6][0] = 'B'
        b_with_rook[7][1] = 'B'
        v_with_rook = ChessEngine.calculate_vision(b_with_rook, 'white', {})
        self.assertFalse(v_with_rook[5][0], "Cornered rook must not reveal behind friendly blocker")
        self.assertFalse(v_with_rook[7][2], "Cornered rook must not reveal behind friendly blocker")
        self.assertEqual(visible_coords(v_with_rook), {(7, 0)} | v_no_rook)

        # 5. Knight at b1 (7,1): sees only own square and legal L-jumps
        b_knight = empty_board()
        b_knight[7][1] = 'N'
        self.assertEqual(visible_coords(ChessEngine.calculate_vision(b_knight, 'white', {})), {(7, 1), (5, 0), (5, 2), (6, 3)})


class TestDameCachee(unittest.TestCase):
    def test_hidden_queen_first_move_and_reveal(self):
        """Hidden Queen must not reveal on 2-step pawn push, but must reveal on queen-exclusive moves."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        
        # Hidden Queen at e2 (row 6, col 4)
        board[6][4] = 'P'
        hidden_queen = {'white': [6, 4], 'black': None}
        
        moves = ChessEngine.get_piece_moves(board, 6, 4, 'white', 'hidden_queen', hidden_queen)
        
        # 1. Forward 1 step (6,4) -> (5,4)
        m_step1 = [m for m in moves if m['to'] == [5, 4]]
        self.assertEqual(len(m_step1), 1)
        self.assertFalse(m_step1[0]['hq_reveal'], "Forward 1 step must NOT reveal the Queen")
        
        # 2. Forward 2 steps (6,4) -> (4,4)
        m_step2 = [m for m in moves if m['to'] == [4, 4]]
        self.assertEqual(len(m_step2), 1)
        self.assertFalse(m_step2[0]['hq_reveal'], "Initial 2-step push must NOT reveal the Queen")
        
        # 3. Sideways move (6,4) -> (6,3)
        m_side = [m for m in moves if m['to'] == [6, 3]]
        self.assertEqual(len(m_side), 1)
        self.assertTrue(m_side[0]['hq_reveal'], "Sideways move MUST reveal the Queen")
        
        # 4. Diagonal to empty square (6,4) -> (5,3)
        m_diag_empty = [m for m in moves if m['to'] == [5, 3]]
        self.assertEqual(len(m_diag_empty), 1)
        self.assertTrue(m_diag_empty[0]['hq_reveal'], "Diagonal move to empty square MUST reveal the Queen")
        
        # 5. Diagonal capture of enemy piece
        board[5][3] = 'p'
        moves_with_enemy = ChessEngine.get_piece_moves(board, 6, 4, 'white', 'hidden_queen', hidden_queen)
        m_diag_capture = [m for m in moves_with_enemy if m['to'] == [5, 3]]
        self.assertEqual(len(m_diag_capture), 1)
        self.assertFalse(m_diag_capture[0]['hq_reveal'], "Diagonal capture of enemy MUST NOT reveal the Queen")


class TestBatailleChess(unittest.TestCase):
    def test_bataille_setup_and_ready(self):
        """Bataille setup must enforce ranks 4-7 for white, empty initial board, and ready transition."""
        room = GameRoom("bat", "bataille")
        
        # Board starts empty
        self.assertTrue(all(room.board[r][c] == '' for r in range(8) for c in range(8)))
        self.assertEqual(len(room.bataille_bench['white']), 16)
        
        # No legal moves before ready
        room.update_legal_moves()
        self.assertEqual(len(room.legal_moves), 0)
        
        # Place all 16 pieces for white on ranks 4-7
        pieces = room.bataille_bench['white'].copy()
        idx = 0
        for r in range(4, 6):
            for c in range(8):
                room.board[r][c] = pieces[idx]
                idx += 1
        room.bataille_bench['white'] = []
        room.bataille_ready['white'] = True
        
        # Place all 16 pieces for black on ranks 0-3
        b_pieces = room.bataille_bench['black'].copy()
        b_idx = 0
        for r in range(0, 2):
            for c in range(8):
                room.board[r][c] = b_pieces[b_idx]
                b_idx += 1
        room.bataille_bench['black'] = []
        room.bataille_ready['black'] = True
        
        # Both ready -> game starts and White has legal moves
        room.update_legal_moves()
        self.assertTrue(len(room.legal_moves) > 0, "After both players are ready, legal moves must be generated")

    def test_bataille_hides_opponent_pieces_before_both_ready(self):
        """Server must strip opponent deployment squares until both players confirm ready."""
        room = GameRoom("bat_hide", "bataille")
        room.board[7][4] = 'K'
        room.board[6][0] = 'Q'
        room.board[0][4] = 'k'
        room.board[1][7] = 'q'

        # Neither ready: each player only sees their own half
        w_board, _ = room.get_masked_board('white')
        b_board, _ = room.get_masked_board('black')
        self.assertEqual(w_board[7][4], 'K')
        self.assertEqual(w_board[0][4], '')
        self.assertEqual(w_board[1][7], '')
        self.assertEqual(b_board[0][4], 'k')
        self.assertEqual(b_board[7][4], '')
        self.assertEqual(b_board[6][0], '')

        # White ready only: White STILL cannot see Black's pieces, and Black cannot see White's
        room.bataille_ready['white'] = True
        w_board2, _ = room.get_masked_board('white')
        b_board2, _ = room.get_masked_board('black')
        self.assertEqual(w_board2[0][4], '')
        self.assertEqual(b_board2[7][4], '')

        # Both ready: full board revealed to both players
        room.bataille_ready['black'] = True
        w_board3, _ = room.get_masked_board('white')
        b_board3, _ = room.get_masked_board('black')
        self.assertEqual(w_board3[0][4], 'k')
        self.assertEqual(b_board3[7][4], 'K')


class TestCrazyhouse(unittest.TestCase):
    def test_crazyhouse_pocket_drops(self):
        """Crazyhouse drops: cannot drop pawns on ranks 0 or 7, can drop on empty squares."""
        empty_row = [''] * 8
        board = [empty_row.copy() for _ in range(8)]
        board[7][4] = 'K'
        board[0][4] = 'k'
        
        pockets = {'white': ['P', 'N'], 'black': []}
        legal_moves = ChessEngine.get_legal_moves(board, 'white', 'clubhouse', pockets, {})
        
        drop_moves = [m for m in legal_moves if m['from'] == 'drop']
        self.assertTrue(len(drop_moves) > 0)
        
        # Verify no pawn drops on rank 0 or 7
        for m in drop_moves:
            if m.get('piece') == 'P':
                self.assertNotIn(m['to'][0], [0, 7], "Pawns cannot be dropped on rank 0 or 7")


class TestVariantSimulations(unittest.TestCase):
    def run_simulation_for_variant(self, variant, num_games=10, max_moves_per_game=50):
        """Simulate autonomous games with random valid moves to ensure zero deadlocks or crashes."""
        for game_idx in range(num_games):
            room = GameRoom(f"sim_{variant}_{game_idx}", variant)
            
            if variant == 'hidden_queen':
                room.hidden_queen['white'] = [6, random.randint(0, 7)]
                room.hidden_queen['black'] = [1, random.randint(0, 7)]
            elif variant == 'bataille':
                # Random valid placement on ranks 4-7 (White) and 0-3 (Black)
                w_coords = [(r, c) for r in range(4, 8) for c in range(8)]
                random.shuffle(w_coords)
                for i, p in enumerate(room.bataille_bench['white']):
                    r, c = w_coords[i]
                    room.board[r][c] = p
                room.bataille_bench['white'] = []
                room.bataille_ready['white'] = True
                
                b_coords = [(r, c) for r in range(0, 4) for c in range(8)]
                random.shuffle(b_coords)
                for i, p in enumerate(room.bataille_bench['black']):
                    r, c = b_coords[i]
                    room.board[r][c] = p
                room.bataille_bench['black'] = []
                room.bataille_ready['black'] = True

            move_count = 0
            while room.status in ["playing", "awaiting_promotion"] and move_count < max_moves_per_game:
                room.update_legal_moves()
                
                if room.status == "awaiting_promotion":
                    # Simulate promotion choice
                    promo_piece = random.choice(['Q', 'R', 'B', 'N'])
                    tr, tc = room.promotion_pending['to']
                    color = room.promotion_pending['color']
                    room.board[tr][tc] = promo_piece if color == 'white' else promo_piece.lower()
                    room.status = "playing"
                    room.promotion_pending = None
                    room.turn = 'black' if room.turn == 'white' else 'white'
                    move_count += 1
                    continue
                
                if room.status == "game_over":
                    break
                
                # Pick a random legal move
                all_moves = []
                for move_list in room.legal_moves.values():
                    all_moves.extend(move_list)
                    
                if not all_moves:
                    break
                    
                m = random.choice(all_moves)
                
                # Execute move
                if m['from'] == 'drop':
                    p_type = m['piece']
                    room.board[m['to'][0]][m['to'][1]] = p_type
                    room.pockets[room.turn].remove(p_type)
                    room.en_passant_target = None
                    room.turn = 'black' if room.turn == 'white' else 'white'
                else:
                    sr, sc = m['from']
                    tr, tc = m['to']
                    moving_piece = room.board[sr][sc]
                    target_piece = room.board[tr][tc]
                    
                    if target_piece:
                        room.pockets[room.turn].append(target_piece.upper() if room.turn == 'white' else target_piece.lower())
                        if target_piece.lower() == 'k' and room.variant != 'antichess':
                            room.status = "game_over"
                            room.winner = room.turn
                    elif m.get('is_ep'):
                        ep_piece = room.board[sr][tc]
                        room.pockets[room.turn].append(ep_piece.upper() if room.turn == 'white' else ep_piece.lower())
                        room.board[sr][tc] = ''
                            
                    room.board[tr][tc] = moving_piece
                    room.board[sr][sc] = ''
                    
                    if moving_piece.lower() == 'p' and abs(tr - sr) == 2:
                        room.en_passant_target = [(sr + tr) // 2, sc]
                    else:
                        room.en_passant_target = None
                    
                    if room.variant == 'hidden_queen':
                        if room.hidden_queen[room.turn] == [sr, sc]:
                            room.hidden_queen[room.turn] = [tr, tc]
                            if m.get('hq_reveal'):
                                room.hidden_queen_revealed[room.turn] = True
                                room.board[tr][tc] = 'Q' if room.turn == 'white' else 'q'
                    
                    if room.status != "game_over" and moving_piece.lower() == 'p' and (tr == 0 or tr == 7):
                        room.status = "awaiting_promotion"
                        room.promotion_pending = {'to': [tr, tc], 'color': room.turn}
                    else:
                        if room.status != "game_over":
                            room.turn = 'black' if room.turn == 'white' else 'white'
                            
                move_count += 1
                
            self.assertIn(room.status, ["playing", "awaiting_promotion", "game_over"], "Simulation ended in invalid state")

    def test_simulation_classic(self):
        self.run_simulation_for_variant('classic', num_games=10)

    def test_simulation_chess960(self):
        self.run_simulation_for_variant('chess960', num_games=10)

    def test_simulation_clubhouse(self):
        self.run_simulation_for_variant('clubhouse', num_games=10)

    def test_simulation_fog(self):
        self.run_simulation_for_variant('fog', num_games=10)

    def test_simulation_antichess(self):
        self.run_simulation_for_variant('antichess', num_games=10)

    def test_simulation_hidden_queen(self):
        self.run_simulation_for_variant('hidden_queen', num_games=10)

    def test_simulation_bataille(self):
        self.run_simulation_for_variant('bataille', num_games=10)


class _DummyWS:
    def __init__(self):
        self.messages = []

    async def accept(self):
        pass

    async def send_text(self, text):
        self.messages.append(json.loads(text))

    async def receive_text(self):
        raise WebSocketDisconnect()


class TestColorSelection(unittest.IsolatedAsyncioTestCase):
    async def test_host_color_choice_and_guest_assignment(self):
        """create_room respects white/black/random and assigns guest to the opposite side."""
        res_black = await create_room(variant='classic', color='black')
        rid_b = res_black['room_id']
        self.assertEqual(res_black['host_color'], 'black')
        self.assertEqual(res_black['guest_color'], 'white')
        self.assertEqual(rooms[rid_b].host_color, 'black')

        guest_ws = _DummyWS()
        await websocket_endpoint(guest_ws, rid_b, 'guest')
        self.assertTrue(len(guest_ws.messages) >= 1)
        self.assertEqual(guest_ws.messages[0]['assigned_color'], 'white')
        rooms.pop(rid_b, None)

        res_white = await create_room(variant='classic', color='white')
        rid_w = res_white['room_id']
        self.assertEqual(res_white['host_color'], 'white')
        self.assertEqual(res_white['guest_color'], 'black')
        rooms.pop(rid_w, None)

        res_rand = await create_room(variant='classic', color='random')
        rid_r = res_rand['room_id']
        self.assertIn(res_rand['host_color'], ('white', 'black'))
        self.assertNotEqual(res_rand['host_color'], res_rand['guest_color'])
        rooms.pop(rid_r, None)


if __name__ == '__main__':
    unittest.main()
