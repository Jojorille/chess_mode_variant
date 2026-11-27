import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

TICK_RATE = 30
TICK_INTERVAL = 1.0 / TICK_RATE
MATCH_DURATION = 300.0

MAX_ENERGY = 20.0
STARTING_ENERGY = 6.0

PHASE_2X_START = 120.0
PHASE_3X_START = 240.0

BASE_ENERGY_RATE = 0.5  # +1 energy every 2.00s (x1)

SPAWN_COSTS = {
    'p': 1,
    'n': 3,
    'b': 3,
    'r': 5,
    'q': 9,
}

ACTIVATION_TIMES = {
    'p': 0.1,
    'n': 1.0,
    'b': 1.0,
    'r': 1.5,
    'q': 2.0,
}

MOVE_COSTS = {
    'p': 1,
    'k': 1,
    'n': 1,
    'b': 1,
    'r': 2,
    'q': 2,
}

COOLDOWN_TIMES = {
    'p': 0.5,
    'k': 1.0,
    'n': 1.0,
    'b': 1.0,
    'r': 1.5,
    'q': 1.5,
}

SPEED_PER_SQUARE = {
    'q': 0.3125,
    'r': 0.3125,
    'b': 0.4375,
    'k': 0.625,
    'p': 0.625,
}

KNIGHT_JUMP_DURATION = 1.3125

# King has rank 0 so any enemy piece (even a Pawn) destroys it on impact;
# King vs King causes mutual destruction (draw).
POWER_RANK = {
    'k': 0,
    'p': 1,
    'n': 3,
    'b': 3,
    'r': 5,
    'q': 9,
}

MATERIAL_SCORE = {
    'p': 1,
    'n': 3,
    'b': 3,
    'r': 5,
    'q': 9,
    'k': 0,
}

COLLISION_RADIUS = 0.45
PROMOTION_CHOICES = ('q', 'r', 'b', 'n')


@dataclass
class ClashPiece:
    """Represents a single unit on the Clash Chess real-time arena."""

    id: str
    color: str
    piece_type: str
    row: int
    col: int
    x: float
    y: float
    state: str = 'ACTIVE'
    state_timer: float = 0.0
    state_duration: float = 0.0
    start_r: int = 0
    start_c: int = 0
    target_r: int = 0
    target_c: int = 0
    move_elapsed: float = 0.0
    move_duration: float = 0.0
    is_airborne: bool = False

    def current_velocity(self) -> Tuple[float, float]:
        """Return linear velocity (vx, vy) in squares/sec while moving."""
        if self.state != 'MOVING' or self.move_duration <= 0.0:
            return (0.0, 0.0)
        return (
            (self.target_c - self.start_c) / self.move_duration,
            (self.target_r - self.start_r) / self.move_duration,
        )

    def current_jump_height(self) -> float:
        """Return normalized parabolic jump height [0..1] for airborne knights."""
        if self.state != 'MOVING' or not self.is_airborne or self.move_duration <= 0.0:
            return 0.0
        progress = max(0.0, min(1.0, self.move_elapsed / self.move_duration))
        return math.sin(math.pi * progress)


class ClashChessEngine:
    """Server-authoritative real-time Clash Chess simulation engine."""

    def __init__(self):
        self.pieces: List[ClashPiece] = [
            ClashPiece(
                id='w_k_0',
                color='white',
                piece_type='k',
                row=7,
                col=4,
                x=4.0,
                y=7.0,
                state='ACTIVE',
            ),
            ClashPiece(
                id='b_k_1',
                color='black',
                piece_type='k',
                row=0,
                col=4,
                x=4.0,
                y=0.0,
                state='ACTIVE',
            ),
        ]
        self.energy: Dict[str, float] = {
            'white': STARTING_ENERGY,
            'black': STARTING_ENERGY,
        }
        self.elapsed_time: float = 0.0
        self.tick_count: int = 0
        self.started: bool = False
        self.status: str = 'waiting'
        self.winner: Optional[str] = None
        self.win_reason: Optional[str] = None
        self.events: List[dict] = []
        self._next_event_id: int = 1
        self._next_piece_id: int = 2

    def start(self) -> None:
        """Begin the real-time match clock and allow player actions."""
        if self.status == 'waiting':
            self.started = True
            self.status = 'playing'

    def get_energy_multiplier(self, t: Optional[float] = None) -> int:
        """Return the active energy regeneration multiplier (1, 2, or 3)."""
        time_sec = self.elapsed_time if t is None else t
        if time_sec >= PHASE_3X_START:
            return 3
        if time_sec >= PHASE_2X_START:
            return 2
        return 1

    @staticmethod
    def _compute_energy_gain(t_start: float, t_end: float) -> float:
        """Integrate piecewise-constant energy regen across [t_start, t_end]."""
        capped_end = min(t_end, MATCH_DURATION)
        if capped_end <= t_start:
            return 0.0

        gain = 0.0
        boundaries = (
            (0.0, PHASE_2X_START, 1.0),
            (PHASE_2X_START, PHASE_3X_START, 2.0),
            (PHASE_3X_START, MATCH_DURATION, 3.0),
        )
        for seg_start, seg_end, mult in boundaries:
            overlap_start = max(t_start, seg_start)
            overlap_end = min(capped_end, seg_end)
            if overlap_end > overlap_start:
                gain += (overlap_end - overlap_start) * BASE_ENERGY_RATE * mult
        return gain

    def get_material_scores(self) -> Dict[str, int]:
        """Compute current material point totals for white and black."""
        scores = {'white': 0, 'black': 0}
        for piece in self.pieces:
            scores[piece.color] += MATERIAL_SCORE.get(piece.piece_type, 0)
        return scores

    def _emit_event(self, kind: str, **payload) -> None:
        event = {
            'id': self._next_event_id,
            'kind': kind,
            't': round(self.elapsed_time, 4),
            **payload,
        }
        self._next_event_id += 1
        self.events.append(event)

    def _get_piece(self, piece_id: str) -> Optional[ClashPiece]:
        for piece in self.pieces:
            if piece.id == piece_id:
                return piece
        return None

    @staticmethod
    def _is_in_spawn_zone(color: str, row: int, col: int) -> bool:
        if not (0 <= row < 8 and 0 <= col < 8):
            return False
        if color == 'white':
            return 4 <= row <= 7
        if color == 'black':
            return 0 <= row <= 3
        return False

    def is_square_empty_for_spawn(self, color: str, row: int, col: int) -> bool:
        """Check whether (row, col) is unoccupied and safe for summoning."""
        for piece in self.pieces:
            if piece.state != 'MOVING':
                if piece.row == row and piece.col == col:
                    return False
            else:
                if piece.color == color and piece.target_r == row and piece.target_c == col:
                    return False
                if not piece.is_airborne:
                    if math.hypot(piece.x - col, piece.y - row) <= COLLISION_RADIUS:
                        return False
                    if round(piece.x) == col and round(piece.y) == row:
                        return False
        return True

    def spawn_piece(
        self, color: str, piece_type: str, row: int, col: int
    ) -> Optional[ClashPiece]:
        """Summon a new piece onto an empty square in the player's own half."""
        if self.status != 'playing' or color not in ('white', 'black'):
            return None

        p_type = str(piece_type).lower()
        if p_type not in SPAWN_COSTS:
            return None
        if not self._is_in_spawn_zone(color, row, col):
            return None

        cost = SPAWN_COSTS[p_type]
        if self.energy[color] + 1e-9 < cost:
            return None
        if not self.is_square_empty_for_spawn(color, row, col):
            return None

        self.energy[color] = max(0.0, self.energy[color] - cost)
        activation_dur = ACTIVATION_TIMES[p_type]
        piece = ClashPiece(
            id=f"{color[0]}_{p_type}_{self._next_piece_id}",
            color=color,
            piece_type=p_type,
            row=row,
            col=col,
            x=float(col),
            y=float(row),
            state='ACTIVATING',
            state_timer=activation_dur,
            state_duration=activation_dur,
        )
        self._next_piece_id += 1
        self.pieces.append(piece)
        self._emit_event('spawn', color=color, piece_type=p_type, row=row, col=col)
        return piece

    def _has_stationary_friendly(self, color: str, row: int, col: int, exclude_id: str) -> bool:
        """Return True if a stationary allied piece currently occupies (row, col)."""
        for other in self.pieces:
            if other.id != exclude_id and other.color == color and other.state != 'MOVING':
                if other.row == row and other.col == col:
                    return True
        return False

    def _has_friendly_block(self, color: str, row: int, col: int, exclude_id: str) -> bool:
        """Return True if a square holds a stationary ally or reserved ally destination."""
        for other in self.pieces:
            if other.id == exclude_id or other.color != color:
                continue
            if other.state != 'MOVING':
                if other.row == row and other.col == col:
                    return True
            elif other.target_r == row and other.target_c == col:
                return True
        return False

    def _has_stationary_enemy(self, color: str, row: int, col: int) -> bool:
        for other in self.pieces:
            if other.color != color and other.state != 'MOVING':
                if other.row == row and other.col == col:
                    return True
        return False

    def _has_grounded_enemy_at_square(self, color: str, row: int, col: int) -> bool:
        """Check whether an enemy targetable by a pawn diagonal attack is at (row, col)."""
        for other in self.pieces:
            if other.color == color or other.is_airborne:
                continue
            if other.state != 'MOVING':
                if other.row == row and other.col == col:
                    return True
            else:
                if abs(other.x - col) <= 0.55 and abs(other.y - row) <= 0.55:
                    return True
        return False

    def get_legal_targets(self, piece_id: str) -> List[List[int]]:
        """Compute all currently legal destination squares for an ACTIVE piece."""
        piece = self._get_piece(piece_id)
        if not piece or self.status != 'playing' or piece.state != 'ACTIVE':
            return []

        sr, sc = piece.row, piece.col
        color = piece.color
        p_type = piece.piece_type
        targets: List[List[int]] = []

        if p_type == 'k':
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = sr + dr, sc + dc
                    if 0 <= nr < 8 and 0 <= nc < 8:
                        if not self._has_friendly_block(color, nr, nc, piece.id):
                            targets.append([nr, nc])
            return targets

        if p_type == 'n':
            jumps = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
            for dr, dc in jumps:
                nr, nc = sr + dr, sc + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    if not self._has_friendly_block(color, nr, nc, piece.id):
                        targets.append([nr, nc])
            return targets

        if p_type in ('r', 'b', 'q'):
            dirs: List[Tuple[int, int]] = []
            if p_type in ('r', 'q'):
                dirs.extend(((-1, 0), (1, 0), (0, -1), (0, 1)))
            if p_type in ('b', 'q'):
                dirs.extend(((-1, -1), (-1, 1), (1, -1), (1, 1)))

            for dr, dc in dirs:
                for step in range(1, 8):
                    nr, nc = sr + dr * step, sc + dc * step
                    if not (0 <= nr < 8 and 0 <= nc < 8):
                        break
                    # Allied pieces block sliding rays just like in real chess.
                    if self._has_stationary_friendly(color, nr, nc, piece.id):
                        break
                    if not self._has_friendly_block(color, nr, nc, piece.id):
                        targets.append([nr, nc])
                    if self._has_stationary_enemy(color, nr, nc):
                        break
            return targets

        if p_type == 'p':
            forward = -1 if color == 'white' else 1
            start_row = 6 if color == 'white' else 1
            r1 = sr + forward
            if 0 <= r1 < 8:
                if not self._has_stationary_enemy(color, r1, sc):
                    if not self._has_friendly_block(color, r1, sc, piece.id):
                        targets.append([r1, sc])
                if sr == start_row:
                    r2 = sr + 2 * forward
                    if 0 <= r2 < 8:
                        if (
                            not self._has_stationary_enemy(color, r1, sc)
                            and not self._has_stationary_friendly(color, r1, sc, piece.id)
                            and not self._has_stationary_enemy(color, r2, sc)
                            and not self._has_friendly_block(color, r2, sc, piece.id)
                        ):
                            targets.append([r2, sc])

                for dc in (-1, 1):
                    nc = sc + dc
                    if 0 <= nc < 8:
                        if not self._has_friendly_block(color, r1, nc, piece.id):
                            if self._has_grounded_enemy_at_square(color, r1, nc):
                                targets.append([r1, nc])
            return targets

        return targets

    def _is_legal_move(self, piece: ClashPiece, tr: int, tc: int) -> bool:
        if not (0 <= tr < 8 and 0 <= tc < 8):
            return False
        if tr == piece.row and tc == piece.col:
            return False
        return [tr, tc] in self.get_legal_targets(piece.id)

    def move_piece(self, color: str, piece_id: str, target_r: int, target_c: int) -> bool:
        """Issue an irrevocable real-time movement command for an ACTIVE piece."""
        if self.status != 'playing':
            return False

        piece = self._get_piece(piece_id)
        if not piece or piece.color != color or piece.state != 'ACTIVE':
            return False

        cost = MOVE_COSTS.get(piece.piece_type)
        if cost is None or self.energy[color] + 1e-9 < cost:
            return False

        if not self._is_legal_move(piece, target_r, target_c):
            return False

        self.energy[color] = max(0.0, self.energy[color] - cost)
        piece.start_r = piece.row
        piece.start_c = piece.col
        piece.target_r = target_r
        piece.target_c = target_c
        piece.x = float(piece.start_c)
        piece.y = float(piece.start_r)
        piece.move_elapsed = 0.0

        if piece.piece_type == 'n':
            piece.move_duration = KNIGHT_JUMP_DURATION
            piece.is_airborne = True
        else:
            chebyshev_dist = max(abs(target_r - piece.start_r), abs(target_c - piece.start_c))
            piece.move_duration = chebyshev_dist * SPEED_PER_SQUARE[piece.piece_type]
            piece.is_airborne = False

        piece.state = 'MOVING'
        piece.state_timer = 0.0
        piece.state_duration = 0.0
        return True

    def promote_piece(self, color: str, piece_id: str, chosen_type: str) -> bool:
        """Promote a pawn on the final rank for 0 energy and 0 cooldown."""
        if self.status != 'playing':
            return False

        piece = self._get_piece(piece_id)
        if not piece or piece.color != color or piece.state != 'PROMOTING':
            return False

        new_type = str(chosen_type).lower()
        if new_type not in PROMOTION_CHOICES:
            return False

        piece.piece_type = new_type
        piece.state = 'ACTIVE'
        piece.state_timer = 0.0
        piece.state_duration = 0.0
        self._emit_event(
            'promote',
            color=color,
            piece_type=new_type,
            row=piece.row,
            col=piece.col,
        )
        return True

    def _find_free_snap_square(
        self,
        piece: ClashPiece,
        pref_r: int,
        pref_c: int,
        destroyed_ids: set,
        extra_blocked: Optional[set] = None,
    ) -> Tuple[int, int]:
        """Find a free grid square near (pref_r, pref_c) without overlapping stationary pieces."""
        occupied = {
            (other.row, other.col)
            for other in self.pieces
            if other.id != piece.id
            and other.id not in destroyed_ids
            and other.state != 'MOVING'
        }
        if extra_blocked:
            occupied.update(extra_blocked)

        if (pref_r, pref_c) not in occupied:
            return (pref_r, pref_c)

        # Backtrack along the piece's travel ray toward its start square.
        dr = piece.start_r - pref_r
        dc = piece.start_c - pref_c
        steps = max(abs(dr), abs(dc), 1) * 2
        for i in range(1, steps + 1):
            frac = i / steps
            cand_r = max(0, min(7, round(pref_r + dr * frac)))
            cand_c = max(0, min(7, round(pref_c + dc * frac)))
            if (cand_r, cand_c) not in occupied:
                return (cand_r, cand_c)

        # Fallback: nearest free square on the board.
        candidates = [
            ((r - pref_r) ** 2 + (c - pref_c) ** 2, r, c)
            for r in range(8)
            for c in range(8)
            if (r, c) not in occupied
        ]
        if candidates:
            candidates.sort()
            return (candidates[0][1], candidates[0][2])
        return (pref_r, pref_c)

    @staticmethod
    def _swept_segment_collision(
        a0: Tuple[float, float],
        a1: Tuple[float, float],
        b0: Tuple[float, float],
        b1: Tuple[float, float],
        s_low: float = 0.0,
    ) -> Optional[float]:
        """Return earliest/closest normalized tick fraction s in [s_low, 1] if distance <= COLLISION_RADIUS."""
        p0x = a0[0] - b0[0]
        p0y = a0[1] - b0[1]
        vx = (a1[0] - a0[0]) - (b1[0] - b0[0])
        vy = (a1[1] - a0[1]) - (b1[1] - b0[1])
        vv = vx * vx + vy * vy

        if vv <= 1e-12:
            s_min = s_low
        else:
            s_min = -(p0x * vx + p0y * vy) / vv
            if s_min < s_low:
                s_min = s_low
            elif s_min > 1.0:
                s_min = 1.0

        dx = p0x + s_min * vx
        dy = p0y + s_min * vy
        if dx * dx + dy * dy <= COLLISION_RADIUS * COLLISION_RADIUS:
            return s_min
        return None

    def tick(self, dt: float) -> None:
        """Advance the simulation by dt seconds in deterministic order."""
        if self.status != 'playing' or dt <= 0.0:
            return

        t0 = self.elapsed_time
        t1 = min(MATCH_DURATION, t0 + dt)
        step_dt = t1 - t0
        if step_dt <= 0.0:
            return

        self.tick_count += 1

        # 1. Regenerate energy piecewise across 0..120, 120..240, 240..300s.
        energy_gain = self._compute_energy_gain(t0, t1)
        for color in ('white', 'black'):
            self.energy[color] = min(MAX_ENERGY, self.energy[color] + energy_gain)
        self.elapsed_time = t1

        # 2. Advance ACTIVATING and COOLDOWN timers.
        for piece in self.pieces:
            if piece.state in ('ACTIVATING', 'COOLDOWN'):
                piece.state_timer -= step_dt
                if piece.state_timer <= 1e-9:
                    piece.state = 'ACTIVE'
                    piece.state_timer = 0.0
                    piece.state_duration = 0.0

        # 3. Linearly interpolate MOVING pieces.
        prev_pos: Dict[str, Tuple[float, float]] = {}
        was_moving_ids = set()
        just_arrived_ids = set()
        just_landed_knights: Dict[str, float] = {}

        for piece in self.pieces:
            prev_pos[piece.id] = (piece.x, piece.y)
            if piece.state != 'MOVING':
                continue

            was_moving_ids.add(piece.id)
            piece.move_elapsed += step_dt

            if piece.move_elapsed >= piece.move_duration - 1e-9:
                over = max(0.0, piece.move_elapsed - piece.move_duration)
                piece.x = float(piece.target_c)
                piece.y = float(piece.target_r)
                piece.row = piece.target_r
                piece.col = piece.target_c
                just_arrived_ids.add(piece.id)
                if piece.piece_type == 'n':
                    s_land = max(0.0, min(1.0, 1.0 - (over / step_dt)))
                    just_landed_knights[piece.id] = s_land
                    piece.is_airborne = False
            else:
                progress = piece.move_elapsed / piece.move_duration
                piece.x = piece.start_c + (piece.target_c - piece.start_c) * progress
                piece.y = piece.start_r + (piece.target_r - piece.start_r) * progress

        # 4. Swept collision detection & resolution (opposing captures/hierarchy + allied blocking).
        candidates: List[Tuple[float, ClashPiece, ClashPiece]] = []
        n_pieces = len(self.pieces)

        for i in range(n_pieces):
            p1 = self.pieces[i]
            if p1.is_airborne:
                continue
            for j in range(i + 1, n_pieces):
                p2 = self.pieces[j]
                if p2.is_airborne:
                    continue
                if p1.color == p2.color and p1.id not in was_moving_ids and p2.id not in was_moving_ids:
                    continue

                a0 = (p1.x, p1.y) if p1.id in just_landed_knights else prev_pos[p1.id]
                a1 = (p1.x, p1.y)
                b0 = (p2.x, p2.y) if p2.id in just_landed_knights else prev_pos[p2.id]
                b1 = (p2.x, p2.y)

                # If a knight just landed, only evaluate interactions once it touches down.
                s_low = max(
                    just_landed_knights.get(p1.id, 0.0),
                    just_landed_knights.get(p2.id, 0.0),
                )
                s_hit = self._swept_segment_collision(a0, a1, b0, b1, s_low=s_low)
                if s_hit is not None:
                    candidates.append((s_hit, p1, p2))

        candidates.sort(key=lambda item: (item[0], item[1].id, item[2].id))

        destroyed_ids = set()
        stopped_ids = set()

        for s_hit, p1, p2 in candidates:
            if p1.id in destroyed_ids or p2.id in destroyed_ids:
                continue

            # If either unit already snapped/stopped earlier in this tick, verify actual overlap.
            if p1.id in stopped_ids or p2.id in stopped_ids:
                if math.hypot(p1.x - p2.x, p1.y - p2.y) > COLLISION_RADIUS:
                    continue

            # Allied pieces cannot pass through each other (except airborne Knights, skipped above).
            if p1.color == p2.color:
                p1_moving = (p1.id in was_moving_ids) and (p1.id not in stopped_ids)
                p2_moving = (p2.id in was_moving_ids) and (p2.id not in stopped_ids)
                a0_pos = (p1.x, p1.y) if p1.id in just_landed_knights else prev_pos[p1.id]
                b0_pos = (p2.x, p2.y) if p2.id in just_landed_knights else prev_pos[p2.id]
                dx0 = b0_pos[0] - a0_pos[0]
                dy0 = b0_pos[1] - a0_pos[1]

                if p1_moving and not p2_moving:
                    v1 = p1.current_velocity()
                    moving_away = (
                        p1.id not in just_landed_knights
                        and (v1[0] * dx0 + v1[1] * dy0) < -1e-6
                        and math.hypot(p1.x - p2.x, p1.y - p2.y)
                        > math.hypot(a0_pos[0] - b0_pos[0], a0_pos[1] - b0_pos[1])
                    )
                    to_stop = [] if moving_away else [(p1, p2)]
                elif p2_moving and not p1_moving:
                    v2 = p2.current_velocity()
                    moving_away = (
                        p2.id not in just_landed_knights
                        and (v2[0] * (-dx0) + v2[1] * (-dy0)) < -1e-6
                        and math.hypot(p1.x - p2.x, p1.y - p2.y)
                        > math.hypot(a0_pos[0] - b0_pos[0], a0_pos[1] - b0_pos[1])
                    )
                    to_stop = [] if moving_away else [(p2, p1)]
                elif p1_moving and p2_moving:
                    v1 = p1.current_velocity()
                    v2 = p2.current_velocity()
                    p1_into_p2 = v1[0] * dx0 + v1[1] * dy0 > 1e-6
                    p2_into_p1 = v2[0] * (-dx0) + v2[1] * (-dy0) > 1e-6
                    if p1_into_p2 and not p2_into_p1:
                        to_stop = [(p1, p2)]
                    elif p2_into_p1 and not p1_into_p2:
                        to_stop = [(p2, p1)]
                    elif not p1_into_p2 and not p2_into_p1 and (
                        p1.id not in just_landed_knights
                        and p2.id not in just_landed_knights
                        and math.hypot(p1.x - p2.x, p1.y - p2.y)
                        > math.hypot(a0_pos[0] - b0_pos[0], a0_pos[1] - b0_pos[1])
                    ):
                        to_stop = []
                    else:
                        to_stop = [(p1, p2), (p2, p1)]
                else:
                    to_stop = []

                for mover, blocker in to_stop:
                    m0 = (
                        (mover.x, mover.y)
                        if mover.id in just_landed_knights
                        else prev_pos[mover.id]
                    )
                    hit_x = m0[0] + s_hit * (mover.x - m0[0])
                    hit_y = m0[1] + s_hit * (mover.y - m0[1])
                    pref_r = max(0, min(7, round(hit_y)))
                    pref_c = max(0, min(7, round(hit_x)))
                    blocker_sq = (
                        (blocker.row, blocker.col)
                        if blocker.state != 'MOVING'
                        else (max(0, min(7, round(blocker.y))), max(0, min(7, round(blocker.x))))
                    )
                    snap_r, snap_c = self._find_free_snap_square(
                        mover, pref_r, pref_c, destroyed_ids, extra_blocked={blocker_sq}
                    )
                    mover.row = snap_r
                    mover.col = snap_c
                    mover.x = float(snap_c)
                    mover.y = float(snap_r)
                    mover.is_airborne = False
                    promo_rank = 0 if mover.color == 'white' else 7
                    if mover.piece_type == 'p' and snap_r == promo_rank:
                        mover.state = 'PROMOTING'
                        mover.state_timer = 0.0
                        mover.state_duration = 0.0
                    else:
                        cooldown_dur = COOLDOWN_TIMES[mover.piece_type]
                        mover.state = 'COOLDOWN'
                        mover.state_timer = cooldown_dur
                        mover.state_duration = cooldown_dur
                    stopped_ids.add(mover.id)
                    just_arrived_ids.discard(mover.id)
                continue

            w, b = (p1, p2) if p1.color == 'white' else (p2, p1)
            w_is_moving = (w.id in was_moving_ids) and (w.id not in stopped_ids)
            b_is_moving = (b.id in was_moving_ids) and (b.id not in stopped_ids)

            if w_is_moving and not b_is_moving:
                # Moving attacker always captures an immobile target (ACTIVE, ACTIVATING, COOLDOWN, PROMOTING).
                winner_p, loser_p = w, b
                is_mutual = False
            elif b_is_moving and not w_is_moving:
                # Moving attacker always captures an immobile target.
                winner_p, loser_p = b, w
                is_mutual = False
            else:
                # Ground collision MOVING vs MOVING: apply power hierarchy (K=0 < P=1 < B=N=3 < R=5 < Q=9).
                rank_w = POWER_RANK[w.piece_type]
                rank_b = POWER_RANK[b.piece_type]
                if rank_w == rank_b:
                    winner_p, loser_p = None, None
                    is_mutual = True
                else:
                    winner_p, loser_p = (w, b) if rank_w > rank_b else (b, w)
                    is_mutual = False

            if is_mutual:
                destroyed_ids.add(w.id)
                destroyed_ids.add(b.id)
                mid_x = (w.x + b.x) * 0.5
                mid_y = (w.y + b.y) * 0.5
                self._emit_event(
                    'collision',
                    outcome='mutual',
                    x=round(mid_x, 3),
                    y=round(mid_y, 3),
                    winner_color=None,
                    loser_type=w.piece_type,
                )
            else:
                destroyed_ids.add(loser_p.id)
                outcome = 'king_captured' if loser_p.piece_type == 'k' else 'capture'
                self._emit_event(
                    'collision',
                    outcome=outcome,
                    x=round(loser_p.x, 3),
                    y=round(loser_p.y, 3),
                    winner_color=winner_p.color,
                    loser_type=loser_p.piece_type,
                )

                winner_moving = (winner_p.id in was_moving_ids) and (winner_p.id not in stopped_ids)
                loser_moving = (loser_p.id in was_moving_ids) and (loser_p.id not in stopped_ids)
                if winner_moving:
                    if not loser_moving:
                        pref_r, pref_c = loser_p.row, loser_p.col
                    else:
                        w_p0 = (
                            (winner_p.x, winner_p.y)
                            if winner_p.id in just_landed_knights
                            else prev_pos[winner_p.id]
                        )
                        hit_x = w_p0[0] + s_hit * (winner_p.x - w_p0[0])
                        hit_y = w_p0[1] + s_hit * (winner_p.y - w_p0[1])
                        pref_r = max(0, min(7, round(hit_y)))
                        pref_c = max(0, min(7, round(hit_x)))

                    snap_r, snap_c = self._find_free_snap_square(
                        winner_p, pref_r, pref_c, destroyed_ids
                    )
                    winner_p.row = snap_r
                    winner_p.col = snap_c
                    winner_p.x = float(snap_c)
                    winner_p.y = float(snap_r)
                    winner_p.is_airborne = False
                    promo_rank = 0 if winner_p.color == 'white' else 7
                    if winner_p.piece_type == 'p' and snap_r == promo_rank:
                        winner_p.state = 'PROMOTING'
                        winner_p.state_timer = 0.0
                        winner_p.state_duration = 0.0
                    else:
                        cooldown_dur = COOLDOWN_TIMES[winner_p.piece_type]
                        winner_p.state = 'COOLDOWN'
                        winner_p.state_timer = cooldown_dur
                        winner_p.state_duration = cooldown_dur
                    stopped_ids.add(winner_p.id)
                    just_arrived_ids.discard(winner_p.id)

        if destroyed_ids:
            self.pieces = [p for p in self.pieces if p.id not in destroyed_ids]

        # 5. Finalize surviving units that reached their destination this tick.
        for piece in self.pieces:
            if piece.id in just_arrived_ids and piece.state == 'MOVING':
                piece.is_airborne = False
                promo_rank = 0 if piece.color == 'white' else 7
                if piece.piece_type == 'p' and piece.row == promo_rank:
                    piece.state = 'PROMOTING'
                    piece.state_timer = 0.0
                    piece.state_duration = 0.0
                else:
                    cooldown_dur = COOLDOWN_TIMES[piece.piece_type]
                    piece.state = 'COOLDOWN'
                    piece.state_timer = cooldown_dur
                    piece.state_duration = cooldown_dur

        # 6. Evaluate win conditions AFTER resolving all collisions on this tick.
        has_white_king = any(p.color == 'white' and p.piece_type == 'k' for p in self.pieces)
        has_black_king = any(p.color == 'black' and p.piece_type == 'k' for p in self.pieces)

        if not has_white_king and not has_black_king:
            self.status = 'game_over'
            self.winner = 'draw'
            self.win_reason = 'double_king_capture'
        elif not has_white_king:
            self.status = 'game_over'
            self.winner = 'black'
            self.win_reason = 'king_captured'
        elif not has_black_king:
            self.status = 'game_over'
            self.winner = 'white'
            self.win_reason = 'king_captured'
        elif self.elapsed_time >= MATCH_DURATION - 1e-9:
            scores = self.get_material_scores()
            self.status = 'game_over'
            if scores['white'] > scores['black']:
                self.winner = 'white'
                self.win_reason = 'timeout_material'
            elif scores['black'] > scores['white']:
                self.winner = 'black'
                self.win_reason = 'timeout_material'
            else:
                self.winner = 'draw'
                self.win_reason = 'timeout_draw'

        # 7. Prune old visual events (> 0.6s).
        self.events = [ev for ev in self.events if self.elapsed_time - ev['t'] <= 0.6]

    def resign(self, color: str) -> None:
        """End the match by resignation."""
        if self.status != 'game_over' and color in ('white', 'black'):
            self.status = 'game_over'
            self.winner = 'black' if color == 'white' else 'white'
            self.win_reason = 'resign'

    def get_state_for_player(self, color: str) -> dict:
        """Serialize real-time game state for a player without leaking opponent secrets."""
        pieces_payload = []
        pending_promotions = []

        for piece in self.pieces:
            vx, vy = piece.current_velocity()
            is_owner = piece.color == color
            if is_owner and piece.state == 'PROMOTING':
                pending_promotions.append(
                    {
                        'piece_id': piece.id,
                        'row': piece.row,
                        'col': piece.col,
                    }
                )
            pieces_payload.append(
                {
                    'id': piece.id,
                    'color': piece.color,
                    'type': piece.piece_type,
                    'x': round(piece.x, 4),
                    'y': round(piece.y, 4),
                    'row': piece.row,
                    'col': piece.col,
                    'state': piece.state,
                    'state_timer': round(max(0.0, piece.state_timer), 4),
                    'state_duration': round(max(0.0, piece.state_duration), 4),
                    'is_airborne': piece.is_airborne,
                    'jump_height': round(piece.current_jump_height(), 4),
                    'vx': round(vx, 4),
                    'vy': round(vy, 4),
                    # Never reveal target square to the opponent.
                    'target': (
                        [piece.target_r, piece.target_c]
                        if (is_owner and piece.state == 'MOVING')
                        else None
                    ),
                }
            )

        return {
            'started': self.started,
            'tick': self.tick_count,
            'elapsed_time': round(self.elapsed_time, 3),
            'time_remaining': round(max(0.0, MATCH_DURATION - self.elapsed_time), 3),
            'match_duration': MATCH_DURATION,
            'energy_multiplier': self.get_energy_multiplier(),
            'my_energy': round(self.energy[color], 4) if color in self.energy else 0.0,
            'max_energy': MAX_ENERGY,
            'scores': self.get_material_scores(),
            'win_reason': self.win_reason,
            'pending_promotions': pending_promotions,
            'pieces': pieces_payload,
            'events': list(self.events),
        }
