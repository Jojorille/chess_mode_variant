import asyncio
import json
import time
import unittest
from fastapi import WebSocketDisconnect

from clash_chess import (
    ACTIVATION_TIMES,
    COOLDOWN_TIMES,
    KNIGHT_JUMP_DURATION,
    MATCH_DURATION,
    MAX_ENERGY,
    MOVE_COSTS,
    SPAWN_COSTS,
    SPEED_PER_SQUARE,
    STARTING_ENERGY,
    ClashChessEngine,
)
from app import GameRoom, broadcast_state, run_clash_loop, rooms, websocket_endpoint


class TestClashChessInitAndEnergy(unittest.TestCase):
    def test_initial_board_and_state(self):
        """Board starts with only White King at e1 (7,4) and Black King at e8 (0,4), energy 6/20."""
        engine = ClashChessEngine()
        self.assertEqual(engine.status, 'waiting')
        self.assertFalse(engine.started)
        self.assertEqual(len(engine.pieces), 2)

        wk = next(p for p in engine.pieces if p.color == 'white')
        bk = next(p for p in engine.pieces if p.color == 'black')
        self.assertEqual((wk.piece_type, wk.row, wk.col, wk.state), ('k', 7, 4, 'ACTIVE'))
        self.assertEqual((bk.piece_type, bk.row, bk.col, bk.state), ('k', 0, 4, 'ACTIVE'))

        self.assertEqual(engine.energy['white'], STARTING_ENERGY)
        self.assertEqual(engine.energy['black'], STARTING_ENERGY)
        self.assertEqual(engine.get_material_scores(), {'white': 0, 'black': 0})

        # Tick before start() must do nothing.
        engine.tick(1.0)
        self.assertEqual(engine.elapsed_time, 0.0)
        self.assertEqual(engine.energy['white'], STARTING_ENERGY)

    def test_energy_regeneration_and_accelerations(self):
        """Verify 0..2:00 (x1), 2:00..4:00 (x2), and 4:00..5:00 (x3) rates and capping at 20."""
        engine = ClashChessEngine()
        engine.start()

        # Drain energy to 0 to test 0 -> 20 in 40.0s at x1 (+0.5/s, +1 every 2.00s).
        engine.energy['white'] = 0.0
        engine.tick(2.0)
        self.assertAlmostEqual(engine.energy['white'], 1.0, places=6)
        self.assertEqual(engine.get_energy_multiplier(), 1)

        engine.tick(38.0)  # total elapsed = 40.0s
        self.assertAlmostEqual(engine.energy['white'], 20.0, places=6)

        # Capped at MAX_ENERGY = 20.
        engine.tick(5.0)
        self.assertEqual(engine.energy['white'], MAX_ENERGY)

        # Advance to 119.0s, drain energy, step 2.0s across 120.0s boundary:
        # 1.0s * 0.5 + 1.0s * 1.0 = 1.5.
        engine.tick(119.0 - engine.elapsed_time)
        self.assertAlmostEqual(engine.elapsed_time, 119.0, places=6)
        self.assertEqual(engine.get_energy_multiplier(), 1)
        engine.energy['white'] = 0.0
        engine.tick(2.0)  # elapsed = 121.0s
        self.assertAlmostEqual(engine.energy['white'], 1.5, places=6)
        self.assertEqual(engine.get_energy_multiplier(), 2)

        # At x2 (2:00..4:00): +1 energy every 1.00s.
        engine.energy['white'] = 0.0
        engine.tick(1.0)
        self.assertAlmostEqual(engine.energy['white'], 1.0, places=6)

        # Advance to 239.0s, drain energy, step 2.0s across 240.0s boundary:
        # 1.0s * 1.0 + 1.0s * 1.5 = 2.5.
        engine.tick(239.0 - engine.elapsed_time)
        self.assertEqual(engine.get_energy_multiplier(), 2)
        engine.energy['white'] = 0.0
        engine.tick(2.0)  # elapsed = 241.0s
        self.assertAlmostEqual(engine.energy['white'], 2.5, places=6)
        self.assertEqual(engine.get_energy_multiplier(), 3)

        # At x3 (4:00..5:00): +1.5/s (+1 every ~0.667s).
        engine.energy['white'] = 0.0
        engine.tick(2.0 / 3.0)
        self.assertAlmostEqual(engine.energy['white'], 1.0, places=6)

    def test_energy_and_target_privacy(self):
        """Player state payload must never expose opponent energy or opponent move targets."""
        engine = ClashChessEngine()
        engine.start()
        engine.energy['white'] = 14.0
        engine.energy['black'] = 3.0

        wq = engine.spawn_piece('white', 'q', 7, 3)
        self.assertIsNotNone(wq)
        engine.tick(ACTIVATION_TIMES['q'])
        self.assertTrue(engine.move_piece('white', wq.id, 3, 3))

        w_state = engine.get_state_for_player('white')
        b_state = engine.get_state_for_player('black')

        self.assertAlmostEqual(w_state['my_energy'], engine.energy['white'], places=3)
        self.assertAlmostEqual(b_state['my_energy'], engine.energy['black'], places=3)
        self.assertNotIn('energy', w_state)
        self.assertNotIn('opponent_energy', w_state)

        w_view_of_wq = next(p for p in w_state['pieces'] if p['id'] == wq.id)
        b_view_of_wq = next(p for p in b_state['pieces'] if p['id'] == wq.id)
        self.assertEqual(w_view_of_wq['target'], [3, 3])
        self.assertIsNone(b_view_of_wq['target'])


class TestClashChessSpawnAndMovement(unittest.TestCase):
    def test_spawn_zones_costs_and_activation_cycle(self):
        """Verify spawn zone boundaries, unlimited duplicates, costs, and ACTIVATING->ACTIVE cycle."""
        engine = ClashChessEngine()
        engine.start()
        engine.energy['white'] = 20.0
        engine.energy['black'] = 20.0

        # Cannot spawn in opponent half or occupied square (e1 = 7,4).
        self.assertIsNone(engine.spawn_piece('white', 'p', 3, 0))
        self.assertIsNone(engine.spawn_piece('white', 'p', 7, 4))
        self.assertIsNone(engine.spawn_piece('black', 'p', 4, 0))
        self.assertIsNone(engine.spawn_piece('black', 'p', 0, 4))

        # Multiple queens allowed on white half (rows 4..7).
        q1 = engine.spawn_piece('white', 'q', 4, 0)
        q2 = engine.spawn_piece('white', 'q', 4, 1)
        self.assertIsNotNone(q1)
        self.assertIsNotNone(q2)
        self.assertAlmostEqual(engine.energy['white'], 20.0 - 2 * SPAWN_COSTS['q'], places=6)
        self.assertEqual(q1.state, 'ACTIVATING')
        self.assertAlmostEqual(q1.state_timer, ACTIVATION_TIMES['q'], places=6)

        # Cannot move while ACTIVATING.
        self.assertFalse(engine.move_piece('white', q1.id, 3, 0))

        # After 1.9s still activating; after +0.1s becomes ACTIVE.
        engine.tick(1.9)
        self.assertEqual(q1.state, 'ACTIVATING')
        engine.tick(0.1)
        self.assertEqual(q1.state, 'ACTIVE')

        # Verify all spawn costs & activation times.
        for p_type, expected_cost in SPAWN_COSTS.items():
            engine.energy['black'] = 20.0
            col = list(SPAWN_COSTS.keys()).index(p_type)
            piece = engine.spawn_piece('black', p_type, 2, col)
            self.assertIsNotNone(piece)
            self.assertAlmostEqual(engine.energy['black'], 20.0 - expected_cost, places=6)
            self.assertAlmostEqual(piece.state_duration, ACTIVATION_TIMES[p_type], places=6)

    def test_linear_speeds_irrevocability_and_cooldowns(self):
        """Verify strictly constant linear velocities, irrevocable moves, and cooldown durations."""
        engine = ClashChessEngine()
        engine.start()
        engine.energy['white'] = 20.0

        # Rook moves 4 squares (6,0) -> (2,0) at 0.3125s/sq = 1.25s total.
        rook = engine.spawn_piece('white', 'r', 6, 0)
        engine.tick(ACTIVATION_TIMES['r'])
        self.assertEqual(rook.state, 'ACTIVE')
        self.assertTrue(engine.move_piece('white', rook.id, 2, 0))
        self.assertEqual(rook.state, 'MOVING')

        # Irrevocable: cannot redirect while MOVING.
        self.assertFalse(engine.move_piece('white', rook.id, 6, 0))

        # Check exact linear interpolation at 25%, 50%, 75%, 100%.
        for step in (1, 2, 3):
            engine.tick(0.3125)
            self.assertAlmostEqual(rook.y, 6.0 - step, places=5)
            self.assertAlmostEqual(rook.x, 0.0, places=5)
        engine.tick(0.3125)
        self.assertEqual((rook.row, rook.col), (2, 0))
        self.assertEqual(rook.state, 'COOLDOWN')
        self.assertAlmostEqual(rook.state_duration, COOLDOWN_TIMES['r'], places=6)
        self.assertFalse(engine.move_piece('white', rook.id, 2, 5))

        engine.tick(COOLDOWN_TIMES['r'])
        self.assertEqual(rook.state, 'ACTIVE')

        # Bishop 4 squares diagonal at 0.4375s/sq = 1.75s total.
        engine.energy['white'] = 20.0
        bishop = engine.spawn_piece('white', 'b', 7, 0)
        engine.tick(ACTIVATION_TIMES['b'])
        self.assertTrue(engine.move_piece('white', bishop.id, 3, 4))
        engine.tick(0.875)  # 50%
        self.assertAlmostEqual(bishop.x, 2.0, places=5)
        self.assertAlmostEqual(bishop.y, 5.0, places=5)
        engine.tick(0.875)
        self.assertEqual((bishop.row, bishop.col), (3, 4))
        self.assertEqual(bishop.state, 'COOLDOWN')
        self.assertAlmostEqual(bishop.state_duration, COOLDOWN_TIMES['b'], places=6)

        # Verify speed & cost tables match rebalanced specification (-20% speed).
        self.assertEqual(SPEED_PER_SQUARE, {'q': 0.3125, 'r': 0.3125, 'b': 0.4375, 'k': 0.625, 'p': 0.625})
        self.assertEqual(KNIGHT_JUMP_DURATION, 1.3125)
        self.assertEqual(MOVE_COSTS, {'p': 1, 'k': 1, 'n': 1, 'b': 1, 'r': 2, 'q': 2})
        self.assertEqual(COOLDOWN_TIMES, {'p': 0.5, 'k': 1.0, 'n': 1.0, 'b': 1.0, 'r': 1.5, 'q': 1.5})

    def test_allied_blocking_simultaneous_moves_and_pawn_rules(self):
        """Allies block rays & pawn 2-step (Knights still jump); simultaneous moves, dodge completion, free promotion."""
        engine = ClashChessEngine()
        engine.start()
        engine.energy['white'] = 20.0
        engine.energy['black'] = 20.0

        # Spawn white pawn on 2nd rank (6, 2), white rook behind it on (7, 2), white knight on (7, 1), white rook on (7, 0).
        wp = engine.spawn_piece('white', 'p', 6, 2)
        wr_blocked = engine.spawn_piece('white', 'r', 7, 2)
        wn = engine.spawn_piece('white', 'n', 7, 1)
        wr_free = engine.spawn_piece('white', 'r', 7, 0)
        # Black rook at (3, 1) (fast enough to dodge sideways before pawn impact).
        br = engine.spawn_piece('black', 'r', 3, 1)
        engine.tick(2.0)

        # Stationary allied pawn at (6, 2) blocks white rook at (7, 2) from passing through file 2.
        wr_blocked_targets = engine.get_legal_targets(wr_blocked.id)
        self.assertNotIn([6, 2], wr_blocked_targets)
        self.assertNotIn([5, 2], wr_blocked_targets)
        self.assertNotIn([2, 2], wr_blocked_targets)
        self.assertIn([7, 3], wr_blocked_targets)  # Sideways on rank 7 is still clear up to King at (7, 4).
        self.assertFalse(engine.move_piece('white', wr_blocked.id, 2, 2))

        # Stationary ally directly in front of a pawn blocks its 2-square advance too.
        wp_blocker = engine.spawn_piece('white', 'p', 5, 2)
        engine.tick(0.2)
        self.assertNotIn([4, 2], engine.get_legal_targets(wp.id))
        self.assertNotIn([5, 2], engine.get_legal_targets(wp.id))
        # Remove temporary blocker to continue pawn test.
        engine.pieces = [p for p in engine.pieces if p.id != wp_blocker.id]

        # Knight CAN still jump over allied pieces cleanly.
        self.assertIn([5, 2], engine.get_legal_targets(wn.id))

        # Simultaneous moves on independent files still work: pawn (6,2)->(4,2) & rook (7,0)->(2,0).
        self.assertTrue(engine.move_piece('white', wp.id, 4, 2))
        self.assertTrue(engine.move_piece('white', wr_free.id, 2, 0))
        engine.tick(1.65)  # Rook arrives in 1.5625s, pawn arrives in 1.25s.
        self.assertEqual((wp.row, wp.col), (4, 2))
        self.assertEqual((wr_free.row, wr_free.col), (2, 0))

        # Wait cooldowns; black rook is at (3,1) diagonally ahead of white pawn at (4,2).
        engine.tick(2.0)
        self.assertTrue(engine.move_piece('white', wp.id, 3, 1))
        # Target dodges sideways immediately (0.3125s to clear (3,1) -> (3,0))!
        self.assertTrue(engine.move_piece('black', br.id, 3, 0))
        engine.tick(0.65)
        # White pawn STILL finishes its diagonal move onto (3,1) even after target dodged.
        self.assertEqual((wp.row, wp.col), (3, 1))
        self.assertIn(wp.id, {p.id for p in engine.pieces})

        # Free promotion with 0 energy and 0 cooldown: move pawn to (1,1) -> (0,1).
        engine.tick(1.0)
        wp.row = 1
        wp.col = 1
        wp.x = 1.0
        wp.y = 1.0
        wp.state = 'ACTIVE'
        engine.energy['white'] = 1.0  # Just enough to pay the 1-energy move.
        self.assertTrue(engine.move_piece('white', wp.id, 0, 1))
        engine.tick(0.625)
        self.assertEqual(wp.state, 'PROMOTING')
        self.assertAlmostEqual(engine.energy['white'], 0.3125, places=6)  # 0.625s * 0.5 = 0.3125 regenerated

        # Promote at 0 energy cost and immediately ACTIVE.
        engine.energy['white'] = 0.0
        self.assertTrue(engine.promote_piece('white', wp.id, 'q'))
        self.assertEqual(wp.piece_type, 'q')
        self.assertEqual(wp.state, 'ACTIVE')
        self.assertEqual(engine.energy['white'], 0.0)

    def test_mid_flight_allied_blocking_without_destruction(self):
        """Mid-flight allied blocking stops the blocked mover cleanly in COOLDOWN with zero friendly fire."""
        # 1. Faster Rook chasing slower moving Pawn on same file stops behind Pawn; Pawn reaches destination.
        engine = ClashChessEngine()
        engine.start()
        engine.energy['white'] = 20.0
        wp = engine.spawn_piece('white', 'p', 6, 2)
        wr = engine.spawn_piece('white', 'r', 7, 2)
        engine.tick(2.0)

        # Pawn begins double-push (6,2)->(4,2), vacating (6,2) as a moving piece; Rook then chases to (2,2).
        self.assertTrue(engine.move_piece('white', wp.id, 4, 2))
        self.assertTrue(engine.move_piece('white', wr.id, 2, 2))
        for _ in range(60):  # 2.0s at 30 Hz
            engine.tick(1.0 / 30.0)

        ids = {p.id for p in engine.pieces}
        self.assertIn(wp.id, ids)
        self.assertIn(wr.id, ids)
        self.assertEqual((wp.row, wp.col), (4, 2))
        self.assertEqual(wr.col, 2)
        self.assertGreater(wr.row, wp.row)  # Rook stopped behind Pawn, never overtook it.

        # 2. Newly spawned ally in front of a moving Rook blocks the Rook cleanly before the ally.
        engine2 = ClashChessEngine()
        engine2.start()
        engine2.energy['white'] = 20.0
        wr2 = engine2.spawn_piece('white', 'r', 7, 0)
        engine2.tick(2.0)
        self.assertTrue(engine2.move_piece('white', wr2.id, 2, 0))
        engine2.tick(0.1)  # Rook is mid-flight near row 6.68
        blocker = engine2.spawn_piece('white', 'p', 5, 0)
        self.assertIsNotNone(blocker)
        for _ in range(45):
            engine2.tick(1.0 / 30.0)

        self.assertIn(wr2.id, {p.id for p in engine2.pieces})
        self.assertIn(blocker.id, {p.id for p in engine2.pieces})
        self.assertEqual((blocker.row, blocker.col), (5, 0))
        self.assertEqual((wr2.row, wr2.col), (6, 0))
        self.assertNotEqual(wr2.state, 'MOVING')

        # 3. Bishop squeezing diagonally between two orthogonally adjacent allies passes cleanly.
        engine3 = ClashChessEngine()
        engine3.start()
        engine3.energy['white'] = 20.0
        wb = engine3.spawn_piece('white', 'b', 6, 1)
        a1 = engine3.spawn_piece('white', 'p', 6, 2)
        a2 = engine3.spawn_piece('white', 'p', 5, 1)
        engine3.tick(2.0)
        self.assertIn([4, 3], engine3.get_legal_targets(wb.id))
        self.assertTrue(engine3.move_piece('white', wb.id, 4, 3))
        for _ in range(35):
            engine3.tick(1.0 / 30.0)
        self.assertEqual((wb.row, wb.col), (4, 3))
        self.assertEqual((a1.row, a1.col), (6, 2))
        self.assertEqual((a2.row, a2.col), (5, 1))


class TestClashChessCollisions(unittest.TestCase):
    def test_attacker_always_captures_immobile_target_including_king(self):
        """Pawn, Bishop, and King moving onto a stationary Rook (ACTIVE, ACTIVATING, COOLDOWN) always capture it."""
        for attacker_type in ('p', 'b', 'k'):
            for target_state in ('ACTIVE', 'ACTIVATING', 'COOLDOWN'):
                engine = ClashChessEngine()
                engine.start()
                engine.energy['white'] = 20.0
                engine.energy['black'] = 20.0

                if attacker_type == 'k':
                    attacker = next(p for p in engine.pieces if p.color == 'white' and p.piece_type == 'k')
                    attacker.row, attacker.col, attacker.x, attacker.y = 3, 2, 2.0, 3.0
                elif attacker_type == 'p':
                    attacker = engine.spawn_piece('white', 'p', 4, 3)
                    engine.tick(ACTIVATION_TIMES['p'])
                    attacker.row, attacker.col, attacker.x, attacker.y = 3, 3, 3.0, 3.0
                else:  # 'b'
                    attacker = engine.spawn_piece('white', 'b', 4, 4)
                    engine.tick(ACTIVATION_TIMES['b'])

                rook = engine.spawn_piece('black', 'r', 2, 2)
                if target_state == 'ACTIVE':
                    engine.tick(ACTIVATION_TIMES['r'])
                elif target_state == 'COOLDOWN':
                    engine.tick(ACTIVATION_TIMES['r'])
                    rook.state = 'COOLDOWN'
                    rook.state_timer = 1.5
                    rook.state_duration = 1.5

                self.assertTrue(engine.move_piece('white', attacker.id, 2, 2))
                dur = 2 * SPEED_PER_SQUARE['b'] if attacker_type == 'b' else SPEED_PER_SQUARE[attacker_type]

                steps = int(dur * 30) + 5
                for _ in range(steps):
                    engine.tick(1.0 / 30.0)

                alive_ids = {p.id for p in engine.pieces}
                self.assertIn(attacker.id, alive_ids, f"{attacker_type} should capture stationary Rook ({target_state})")
                self.assertNotIn(rook.id, alive_ids, f"Stationary Rook ({target_state}) must be captured by {attacker_type}")
                self.assertEqual((attacker.row, attacker.col), (2, 2))
                self.assertIn(attacker.state, ('COOLDOWN', 'ACTIVE'))

        # Verify Pawn capturing a stationary Rook on the promotion rank triggers PROMOTING.
        e_promo = ClashChessEngine()
        e_promo.start()
        e_promo.energy['white'] = 20.0
        e_promo.energy['black'] = 20.0
        wp = e_promo.spawn_piece('white', 'p', 4, 2)
        br = e_promo.spawn_piece('black', 'r', 0, 3)
        e_promo.tick(2.0)
        wp.row, wp.col, wp.x, wp.y = 1, 2, 2.0, 1.0
        self.assertTrue(e_promo.move_piece('white', wp.id, 0, 3))
        e_promo.tick(SPEED_PER_SQUARE['p'])
        alive_promo = {p.id for p in e_promo.pieces}
        self.assertIn(wp.id, alive_promo)
        self.assertNotIn(br.id, alive_promo)
        self.assertEqual((wp.row, wp.col), (0, 3))
        self.assertEqual(wp.state, 'PROMOTING')

    def test_power_hierarchy_only_applies_moving_vs_moving(self):
        """Hierarchy (P < B < R < Q) applies when BOTH ground pieces are MOVING; moving vs immobile always captures."""
        moving_pairs = [
            ('q', 'r'),
            ('r', 'b'),
            ('b', 'p'),
            ('q', 'p'),
        ]
        for strong, weak in moving_pairs:
            engine = ClashChessEngine()
            engine.start()
            engine.energy['white'] = 20.0
            engine.energy['black'] = 20.0

            if strong == 'b':
                # White Bishop (5,5)->(1,1) crosses Black Pawn (2,3)->(4,3)? Put them head-on on diagonal/file:
                # White Bishop (4,4)->(2,2) meets Black Pawn (2,3)->(3,3) or Pawn (1,3)->(3,3) -> diagonal (3,3)!
                # White Bishop (4,4)->(2,2) hits (3,3) at t = 0.4375s; Black Pawn (2,3)->(3,3) hits (3,3) at t = 0.625s -> collide near (3,3)!
                w_piece = engine.spawn_piece('white', 'b', 4, 4)
                b_piece = engine.spawn_piece('black', 'p', 2, 3)
                engine.tick(2.0)
                self.assertTrue(engine.move_piece('black', b_piece.id, 3, 3))
                self.assertTrue(engine.move_piece('white', w_piece.id, 2, 2))
            elif weak == 'b':
                # White Rook (5,2)->(1,2) passes (3,2) at 0.625s; Black Bishop (1,0)->(4,3) passes (3,2) at 0.875s -> collide at (3,2)!
                w_piece = engine.spawn_piece('white', 'r', 5, 2)
                b_piece = engine.spawn_piece('black', 'b', 1, 0)
                engine.tick(2.0)
                self.assertTrue(engine.move_piece('black', b_piece.id, 4, 3))
                self.assertTrue(engine.move_piece('white', w_piece.id, 1, 2))
            else:
                # Head-on on file 0: White (strong) (6,0)->(0,0) vs Black (weak) (1,0)->(3,0) or (5,0).
                w_piece = engine.spawn_piece('white', strong, 6, 0)
                b_piece = engine.spawn_piece('black', weak, 1, 0)
                engine.tick(2.5)
                b_target_r = 3 if weak == 'p' else 5
                self.assertTrue(engine.move_piece('black', b_piece.id, b_target_r, 0))
                self.assertTrue(engine.move_piece('white', w_piece.id, 0, 0))

            for _ in range(60):  # 2.0s at 30 Hz
                engine.tick(1.0 / 30.0)

            alive_ids = {p.id for p in engine.pieces}
            self.assertIn(w_piece.id, alive_ids, f"MOVING {strong} must destroy MOVING {weak}")
            self.assertNotIn(b_piece.id, alive_ids, f"MOVING {weak} must be destroyed by MOVING {strong}")
            self.assertEqual(w_piece.x, float(w_piece.col))
            self.assertEqual(w_piece.y, float(w_piece.row))

        # Verify King (even MOVING) loses immediately when colliding with a MOVING enemy piece.
        e_king = ClashChessEngine()
        e_king.start()
        e_king.energy['white'] = 20.0
        e_king.energy['black'] = 20.0
        wk = next(p for p in e_king.pieces if p.color == 'white' and p.piece_type == 'k')
        wk.row, wk.col, wk.x, wk.y = 4, 2, 2.0, 4.0
        bp = e_king.spawn_piece('black', 'p', 2, 2)
        e_king.tick(0.5)
        self.assertTrue(e_king.move_piece('black', bp.id, 3, 2))
        self.assertTrue(e_king.move_piece('white', wk.id, 3, 2))
        for _ in range(30):
            e_king.tick(1.0 / 30.0)
        self.assertEqual(e_king.status, 'game_over')
        self.assertEqual(e_king.winner, 'black')
        self.assertEqual(e_king.win_reason, 'king_captured')

    def test_moving_clash_stops_stronger_piece_immediately(self):
        """Head-on collision in mid-board destroys weaker moving piece and snaps stronger to grid + COOLDOWN."""
        engine = ClashChessEngine()
        engine.start()
        engine.energy['white'] = 20.0
        engine.energy['black'] = 20.0

        wq = engine.spawn_piece('white', 'q', 6, 0)
        bp = engine.spawn_piece('black', 'p', 1, 0)
        engine.tick(2.0)

        # Black pawn moves first so it is MOVING (non-blocking ray), then Queen targets past it.
        self.assertTrue(engine.move_piece('black', bp.id, 3, 0))
        self.assertTrue(engine.move_piece('white', wq.id, 0, 0))

        for _ in range(60):  # 2.0s at 30 Hz
            engine.tick(1.0 / 30.0)

        alive_ids = {p.id for p in engine.pieces}
        self.assertIn(wq.id, alive_ids)
        self.assertNotIn(bp.id, alive_ids)
        # Queen must have stopped on collision square (not continued all the way to (0,0)).
        self.assertGreater(wq.row, 0)
        self.assertEqual(wq.x, float(wq.col))
        self.assertEqual(wq.y, float(wq.row))

    def test_equal_rank_mutual_destruction_moving_vs_moving(self):
        """Equal power ground pieces mutually destroy each other when BOTH are MOVING (R vs R, B vs B, P vs P, Q vs Q)."""
        equal_pairs = [('r', 'r'), ('b', 'b'), ('p', 'p'), ('q', 'q')]
        for wt, bt in equal_pairs:
            engine = ClashChessEngine()
            engine.start()
            engine.energy['white'] = 20.0
            engine.energy['black'] = 20.0

            if wt == 'p':
                wp = engine.spawn_piece('white', 'p', 4, 2)
                bp = engine.spawn_piece('black', 'p', 2, 2)
                engine.tick(1.0)
                self.assertTrue(engine.move_piece('black', bp.id, 3, 2))
                self.assertTrue(engine.move_piece('white', wp.id, 3, 2))
            elif wt == 'b':
                wp = engine.spawn_piece('white', 'b', 5, 5)
                bp = engine.spawn_piece('black', 'b', 1, 1)
                engine.tick(1.5)
                self.assertTrue(engine.move_piece('black', bp.id, 5, 5))
                self.assertTrue(engine.move_piece('white', wp.id, 1, 1))
            else:
                wp = engine.spawn_piece('white', wt, 5, 2)
                bp = engine.spawn_piece('black', bt, 1, 2)
                engine.tick(2.5)
                self.assertTrue(engine.move_piece('black', bp.id, 5, 2))
                self.assertTrue(engine.move_piece('white', wp.id, 1, 2))

            for _ in range(60):
                engine.tick(1.0 / 30.0)

            alive_ids = {p.id for p in engine.pieces}
            self.assertNotIn(wp.id, alive_ids, f"MOVING White {wt} should mutually destruct against MOVING {bt}")
            self.assertNotIn(bp.id, alive_ids, f"MOVING Black {bt} should mutually destruct against MOVING {wt}")

    def test_knight_airborne_invincibility_and_landing_resolution(self):
        """MOVING Knight passes straight through MOVING Queen with zero damage/stop; landing captures immobile targets."""
        engine = ClashChessEngine()
        engine.start()
        engine.energy['white'] = 20.0
        engine.energy['black'] = 20.0

        # White Knight jumps (5, 1) -> (3, 2) (passes midpoint (4.0, 1.5) at t = 0.65625s).
        wn = engine.spawn_piece('white', 'n', 5, 1)
        # Black Queen sweeps right across (4, 0) -> (4, 6), crossing (4.0, 1.5) at t = 0.46875s..0.625s!
        bq_moving = engine.spawn_piece('black', 'q', 3, 7)
        engine.tick(2.0)
        bq_moving.row, bq_moving.col, bq_moving.x, bq_moving.y = 4, 0, 0.0, 4.0

        self.assertTrue(engine.move_piece('white', wn.id, 3, 2))
        self.assertTrue(engine.move_piece('black', bq_moving.id, 4, 6))

        # Step through entire flight before 1.3125s: Knight is completely invincible and neither piece stops!
        for _ in range(36):  # 1.20s
            engine.tick(1.0 / 30.0)
        alive_mid = {p.id for p in engine.pieces}
        self.assertIn(wn.id, alive_mid)
        self.assertIn(bq_moving.id, alive_mid)
        self.assertTrue(wn.is_airborne)
        self.assertEqual(wn.state, 'MOVING')

        # Finish flight: Knight lands cleanly on (3, 2) and Queen finishes at (4, 6).
        for _ in range(30):
            engine.tick(1.0 / 30.0)
        self.assertFalse(wn.is_airborne)
        self.assertEqual((wn.row, wn.col), (3, 2))
        self.assertEqual((bq_moving.row, bq_moving.col), (4, 6))

        # Landing on ANY stationary enemy (even Queen or Rook) captures it!
        for target_type in ('p', 'b', 'r', 'q'):
            e2 = ClashChessEngine()
            e2.start()
            e2.energy['white'] = 20.0
            e2.energy['black'] = 20.0
            k_unit = e2.spawn_piece('white', 'n', 5, 1)
            opp = e2.spawn_piece('black', target_type, 3, 2)
            e2.tick(2.5)
            self.assertTrue(e2.move_piece('white', k_unit.id, 3, 2))
            e2.tick(KNIGHT_JUMP_DURATION)
            ids = {p.id for p in e2.pieces}
            self.assertIn(k_unit.id, ids, f"Landing Knight should capture stationary {target_type}")
            self.assertNotIn(opp.id, ids, f"Stationary {target_type} must be captured by landing Knight")
            self.assertEqual((k_unit.row, k_unit.col), (3, 2))

        # Landing at the exact instant a MOVING Queen crosses (3, 2) -> MOVING vs MOVING: Queen destroys Knight!
        e3 = ClashChessEngine()
        e3.start()
        e3.energy['white'] = 20.0
        e3.energy['black'] = 20.0
        k_unit = e3.spawn_piece('white', 'n', 5, 1)
        bq = e3.spawn_piece('black', 'q', 3, 6)
        e3.tick(2.5)
        self.assertTrue(e3.move_piece('white', k_unit.id, 3, 2))
        # Queen moves (3,6) -> (3,0): reaches col 2 (4 squares) at t = 4 * 0.3125 = 1.25s, still within 0.45 at 1.3125s!
        self.assertTrue(e3.move_piece('black', bq.id, 3, 0))
        for _ in range(45):  # 1.50s
            e3.tick(1.0 / 30.0)
        ids3 = {p.id for p in e3.pieces}
        self.assertNotIn(k_unit.id, ids3)
        self.assertIn(bq.id, ids3)


class TestClashChessWinAndTimeout(unittest.TestCase):
    def test_king_capture_and_simultaneous_king_draw(self):
        """Any piece (even Pawn) capturing King wins immediately; both Kings dying on same tick is draw."""
        engine = ClashChessEngine()
        engine.start()
        engine.energy['white'] = 20.0
        engine.energy['black'] = 20.0

        wp = engine.spawn_piece('white', 'p', 4, 4)
        engine.tick(0.5)
        wp.row, wp.col, wp.x, wp.y = 1, 3, 3.0, 1.0
        # Pawn captures Black King diagonally at (0, 4) in 0.625s.
        self.assertTrue(engine.move_piece('white', wp.id, 0, 4))
        engine.tick(0.625)
        self.assertEqual(engine.status, 'game_over')
        self.assertEqual(engine.winner, 'white')
        self.assertEqual(engine.win_reason, 'king_captured')

        # Simultaneous double King destruction on exact same tick -> draw.
        e2 = ClashChessEngine()
        e2.start()
        e2.energy['white'] = 20.0
        e2.energy['black'] = 20.0
        wq = e2.spawn_piece('white', 'q', 4, 4)
        bq = e2.spawn_piece('black', 'q', 3, 4)
        e2.tick(2.0)

        # White Queen 4 squares from Black King (0,4) -> 1.25s; Black Queen 4 squares from White King (7,4) -> 1.25s.
        # Put Queens on c-file/a-file so they don't collide with each other!
        wq.row, wq.col, wq.x, wq.y = 4, 4, 4.0, 4.0
        bq.row, bq.col, bq.x, bq.y = 3, 0, 0.0, 3.0
        # White Queen (4,4)->(0,4) [4 squares = 1.25s], Black Queen (3,0)->(7,4) [4 squares diagonal = 1.25s].
        self.assertTrue(e2.move_piece('white', wq.id, 0, 4))
        self.assertTrue(e2.move_piece('black', bq.id, 7, 4))
        e2.tick(1.25)
        self.assertEqual(e2.status, 'game_over')
        self.assertEqual(e2.winner, 'draw')
        self.assertEqual(e2.win_reason, 'double_king_capture')

    def test_five_minute_timeout_material_and_draw(self):
        """At 5:00 (300s), higher material score wins; equal material results in draw."""
        e1 = ClashChessEngine()
        e1.start()
        e1.energy['white'] = 20.0
        e1.energy['black'] = 20.0
        e1.spawn_piece('white', 'r', 6, 0)  # 5 pts
        e1.spawn_piece('black', 'n', 1, 0)  # 3 pts

        e1.tick(MATCH_DURATION)
        self.assertEqual(e1.status, 'game_over')
        self.assertEqual(e1.winner, 'white')
        self.assertEqual(e1.win_reason, 'timeout_material')

        # Equal material draw (Bishop 3 vs Knight 3).
        e2 = ClashChessEngine()
        e2.start()
        e2.energy['white'] = 20.0
        e2.energy['black'] = 20.0
        e2.spawn_piece('white', 'b', 6, 0)  # 3 pts
        e2.spawn_piece('black', 'n', 1, 0)  # 3 pts
        e2.tick(MATCH_DURATION)
        self.assertEqual(e2.status, 'game_over')
        self.assertEqual(e2.winner, 'draw')
        self.assertEqual(e2.win_reason, 'timeout_draw')


class FakeWebSocket:
    def __init__(self, incoming=None):
        self.accepted = False
        self.sent_messages = []
        self.incoming = list(incoming or [])

    async def accept(self):
        self.accepted = True

    async def send_text(self, text: str):
        self.sent_messages.append(json.loads(text))

    async def receive_text(self):
        if self.incoming:
            return json.dumps(self.incoming.pop(0))
        await asyncio.sleep(0.05)
        raise WebSocketDisconnect()


class TestClashChessServerIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_loop_tick_rate_and_network_isolation(self):
        """Server tick loop runs >= 30 ticks/sec and isolates energy & target per player."""
        room_id = "test_clash_loop"
        room = GameRoom(room_id, 'clash_chess')
        rooms[room_id] = room

        ws_white = FakeWebSocket()
        ws_black = FakeWebSocket()
        room.players['white'] = ws_white
        room.players['black'] = ws_black

        room.clash_engine.start()
        room.status = 'playing'
        task = asyncio.create_task(run_clash_loop(room))
        room.clash_task = task

        # Trigger a white move and set asymmetric energy to check privacy across broadcasts.
        room.clash_engine.energy['white'] = 15.0
        room.clash_engine.energy['black'] = 2.0
        wq = room.clash_engine.spawn_piece('white', 'q', 7, 3)
        wq.state = 'ACTIVE'
        wq.state_timer = 0.0
        room.clash_engine.move_piece('white', wq.id, 4, 3)

        start = time.monotonic()
        await asyncio.sleep(0.55)
        elapsed = time.monotonic() - start
        ticks = room.clash_engine.tick_count

        room.clash_engine.resign('black')
        room.status = room.clash_engine.status
        room.winner = room.clash_engine.winner
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await broadcast_state(room)
        rooms.pop(room_id, None)

        self.assertGreaterEqual(ticks / elapsed, 30.0, f"Expected >= 30 ticks/sec, got {ticks / elapsed:.2f}")
        self.assertTrue(len(ws_white.sent_messages) >= 10)
        self.assertTrue(len(ws_black.sent_messages) >= 10)

        w_sample = ws_white.sent_messages[0]['clash']
        b_sample = ws_black.sent_messages[0]['clash']
        self.assertNotAlmostEqual(w_sample['my_energy'], b_sample['my_energy'], places=1)

        w_q = next(p for p in w_sample['pieces'] if p['id'] == wq.id)
        b_q = next(p for p in b_sample['pieces'] if p['id'] == wq.id)
        self.assertEqual(w_q['target'], [4, 3])
        self.assertIsNone(b_q['target'])

        self.assertEqual(ws_white.sent_messages[-1]['status'], 'game_over')
        self.assertEqual(ws_white.sent_messages[-1]['winner'], 'white')

    async def test_websocket_endpoint_auto_start_and_actions(self):
        """Joining both players starts the match and processes clash_spawn & resign."""
        room_id = "test_clash_ws"
        room = GameRoom(room_id, 'clash_chess')
        rooms[room_id] = room

        ws_white = FakeWebSocket()
        room.players['white'] = ws_white
        ws_black = FakeWebSocket(incoming=[
            {'type': 'clash_spawn', 'piece': 'p', 'row': 1, 'col': 0},
            {'type': 'resign'},
        ])

        await websocket_endpoint(ws_black, room_id, 'black')
        if room.clash_task and not room.clash_task.done():
            room.clash_task.cancel()
            await asyncio.gather(room.clash_task, return_exceptions=True)
        rooms.pop(room_id, None)

        self.assertTrue(ws_black.accepted)
        self.assertTrue(room.clash_engine.started)
        self.assertEqual(room.clash_engine.status, 'game_over')
        self.assertEqual(room.clash_engine.winner, 'white')
        self.assertTrue(any(p.color == 'black' and p.piece_type == 'p' for p in room.clash_engine.pieces))


if __name__ == '__main__':
    unittest.main()
