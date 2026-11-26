let game_room = sessionStorage.getItem('chess_room_id') || null;
let player_color = sessionStorage.getItem('chess_player_color') || null;

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.has('join')) {
    const joinId = urlParams.get('join');
    const savedRoom = sessionStorage.getItem('chess_room_id');
    const savedColor = sessionStorage.getItem('chess_player_color');
    game_room = joinId;
    if (savedRoom === joinId && (savedColor === 'white' || savedColor === 'black')) {
        player_color = savedColor;
    } else {
        player_color = 'guest';
        sessionStorage.removeItem('chess_player_color');
    }
    sessionStorage.setItem('chess_room_id', game_room);
}

const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const host = window.location.host || "localhost:8000";

const WS_URL = `${wsProtocol}//${host}/ws`;
const API_URL = `${protocol}//${host}`;

let ws;
let current_state = null;
let selected_pos = null; 

const PIECE_SVG_SHAPES = {
    p: `<path class="piece-body" d="M22.5,9 C19.5,9 17.5,11.3 17.5,14 C17.5,15.9 18.6,17.6 20.2,18.4 C17.3,20 15.5,22.9 15.5,26.3 C15.5,28.8 16.6,31 18.3,32.5 L12.5,36.5 L12.5,39.5 L32.5,39.5 L32.5,36.5 L26.7,32.5 C28.4,31 29.5,28.8 29.5,26.3 C29.5,22.9 27.7,20 24.8,18.4 C26.4,17.6 27.5,15.9 27.5,14 C27.5,11.3 25.5,9 22.5,9 Z"/>
        <path class="piece-detail" d="M14.5,36.5 L30.5,36.5 M18.5,32.5 L26.5,32.5"/>`,
    r: `<path class="piece-body" d="M11,39.5 L34,39.5 L34,36 L11,36 Z M13,36 L15,32 L30,32 L32,36 Z M15,32 L15,18 L12,15 L12,9 L17,9 L17,12.5 L20,12.5 L20,9 L25,9 L25,12.5 L28,12.5 L28,9 L33,9 L33,15 L30,18 L30,32 Z"/>
        <path class="piece-detail" d="M15,18 L30,18 M15,32 L30,32"/>`,
    n: `<path class="piece-body" d="M12,39.5 L33.5,39.5 L33.5,36 L12,36 Z M14,36 C14.5,30 18.5,27 20.5,24.5 C19.5,23 17,22.5 14.5,24 C13.5,24.6 12,24 11.5,22.5 C10.5,20 12.5,16.5 15.5,14 C16,12 16,9.5 17.5,8.5 C18.5,9.5 19.5,11 20,11.8 C22.5,10.8 26,11.5 29,14.5 C32.5,18 33.5,24.5 32.5,36 Z"/>
        <circle class="piece-detail-fill" cx="17.2" cy="16.2" r="1.4"/>
        <path class="piece-detail" d="M14,36 L32,36"/>`,
    b: `<path class="piece-body" d="M11,39.5 L34,39.5 L34,36.5 L28.5,34 C30.5,31.5 31.5,28 31,24 C30.5,19.5 27.5,15.8 24.5,14 C25.3,13.2 25.8,12.1 25.8,10.8 C25.8,9 24.3,7.5 22.5,7.5 C20.7,7.5 19.2,9 19.2,10.8 C19.2,12.1 19.7,13.2 20.5,14 C17.5,15.8 14.5,19.5 14,24 C13.5,28 14.5,31.5 16.5,34 L11,36.5 Z"/>
        <path class="piece-detail" d="M18.5,23.5 L26.5,23.5 M22.5,19.5 L22.5,27.5 M16.5,34 L28.5,34"/>`,
    q: `<path class="piece-body" d="M9,14 C10.4,14 11.5,15.1 11.5,16.5 C11.5,17.2 11.2,17.8 10.8,18.2 L16,25 L16.5,15.4 C15.6,15 15,14.1 15,13 C15,11.6 16.1,10.5 17.5,10.5 C18.9,10.5 20,11.6 20,13 C20,13.9 19.5,14.7 18.8,15.1 L22.5,24.5 L26.2,15.1 C25.5,14.7 25,13.9 25,13 C25,11.6 26.1,10.5 27.5,10.5 C28.9,10.5 30,11.6 30,13 C30,14.1 29.4,15 28.5,15.4 L29,25 L34.2,18.2 C33.8,17.8 33.5,17.2 33.5,16.5 C33.5,15.1 34.6,14 36,14 C37.4,14 38.5,15.1 38.5,16.5 C38.5,17.6 37.8,18.5 36.8,18.8 L32.5,34 L34,36.5 L34,39.5 L11,39.5 L11,36.5 L12.5,34 L8.2,18.8 C7.2,18.5 6.5,17.6 6.5,16.5 C6.5,15.1 7.6,14 9,14 Z"/>
        <path class="piece-detail" d="M12.5,34 L32.5,34 M11.5,36.5 L33.5,36.5"/>`,
    k: `<path class="piece-body" d="M21,6 L24,6 L24,9.5 L27.5,9.5 L27.5,12.5 L24,12.5 L24,16 C28.5,14.5 34.5,16 36,21.5 C37,25.5 34.5,30 32,33.5 L34,36.5 L34,39.5 L11,39.5 L11,36.5 L13,33.5 C10.5,30 8,25.5 9,21.5 C10.5,16 16.5,14.5 21,16 L21,12.5 L17.5,12.5 L17.5,9.5 L21,9.5 Z"/>
        <path class="piece-detail" d="M13,33.5 L32,33.5 M11.5,36.5 L33.5,36.5 M22.5,16 L22.5,33.5"/>`
};

function getPieceSvgMarkup(pieceCharOrType, explicitColor = null) {
    if (!pieceCharOrType) return '';
    const pType = pieceCharOrType.toLowerCase();
    const shape = PIECE_SVG_SHAPES[pType];
    if (!shape) return pieceCharOrType;
    const isWhite = explicitColor
        ? explicitColor === 'white'
        : pieceCharOrType === pieceCharOrType.toUpperCase();
    const colorClass = isWhite ? 'piece-svg-white' : 'piece-svg-black';
    return `<svg class="chess-piece-svg ${colorClass}" viewBox="0 0 45 45" aria-hidden="true">${shape}</svg>`;
}

const VARIANT_NAMES = {
    'classic': 'Classique', 'chess960': 'Chess 960', 'clubhouse': 'Club House',
    'fog': 'Brouillard de Guerre', 'antichess': 'Qui perd gagne',
    'hidden_queen': 'Dame Cachée', 'bataille': 'Bataille Chess',
    'clash_chess': 'Clash Chess (Temps Réel)'
};

const CLASH_SPAWN_COSTS = { p: 1, n: 3, b: 3, r: 5, q: 9 };
const CLASH_MOVE_COSTS = { p: 1, k: 1, n: 1, b: 1, r: 2, q: 2 };
const CLASH_AZERTY_SHORTCUTS = { a: 'p', z: 'n', e: 'b', r: 'r', t: 'q' };
const CLASH_PRECHARGE_WINDOW_SEC = 0.28;
const CLASH_ENERGY_RATES = { 1: 0.5, 2: 1.0, 3: 1.5 };
const CLASH_RATE_LABELS = {
    1: '×1 (+1 / 2.00s)',
    2: '×2 (+1 / 1.00s)',
    3: '×3 (+1 / 0.667s)'
};
const CLASH_RING_CIRCUMFERENCE = 2 * Math.PI * 42;

let clashModeActive = false;
let clashSnapshot = null;
let clashSnapshotTime = 0;
let clashLastFrameTime = 0;
let clashAnimFrameId = null;
let clashBoardCells = [];
let clashPieceNodes = new Map();
let clashTargetNodes = new Map();
let clashEnergySegNodes = [];
let clashEnergyLastWhole = null;
let clashEnergySparks = [];
let clashCardWasAffordable = { p: null, n: null, b: null, r: null, q: null };
let clashHoveredSquare = null;
let clashHoverPreviewKey = '';
let selectedClashDeckPiece = null;
let selectedClashPieceId = null;
let clashDragState = null;
let seenClashEventIds = new Set();
let clashParticles = [];
let clashShockwaves = [];

document.addEventListener('DOMContentLoaded', () => {
    initUI();
    if (game_room && player_color) joinGame(game_room, player_color);
});

function initUI() {
    document.getElementById('create-game-btn').addEventListener('click', async () => {
        const variant = document.getElementById('variant-select').value;
        const chosenColor = document.getElementById('color-select').value;
        try {
            const response = await fetch(
                `${API_URL}/create_room?variant=${encodeURIComponent(variant)}&color=${encodeURIComponent(chosenColor)}`,
                { method: 'POST' }
            );
            const data = await response.json();
            player_color = data.host_color || 'white';
            sessionStorage.setItem('chess_player_color', player_color);
            joinGame(data.room_id, player_color);
        } catch (e) { console.error("Erreur création room", e); }
    });

    document.getElementById('lobby-copy-link-btn').addEventListener('click', () => {
        const linkInput = document.getElementById('lobby-share-link');
        linkInput.select();
        document.execCommand('copy');
        alert("Lien copié !");
    });
    
    document.getElementById('lobby-cancel-btn').addEventListener('click', abandonGame);
    document.getElementById('resign-btn').addEventListener('click', abandonGame);
    
    document.getElementById('bataille-ready-btn').addEventListener('click', () => {
        if (current_state && current_state.bataille_bench.length === 0) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'bataille_ready' }));
            }
        } else {
            alert("Placez toutes vos pièces d'abord !");
        }
    });

    document.querySelectorAll('.promo-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const piece = e.currentTarget.dataset.piece;
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'promote', piece: piece }));
            }
        });
    });

    initClashUI();
}

function abandonGame() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        try {
            ws.send(JSON.stringify({ type: 'resign' }));
        } catch (e) {}
    }
    sessionStorage.removeItem('chess_room_id');
    sessionStorage.removeItem('chess_player_color');
    localStorage.removeItem('chess_room_id');
    localStorage.removeItem('chess_player_color');
    window.location.href = window.location.pathname;
}

function joinGame(room_id, color) {
    game_room = room_id;
    player_color = color;
    sessionStorage.setItem('chess_room_id', game_room);
    
    document.getElementById('header').classList.add('hidden');
    const shareUrl = new URL(window.location.href);
    shareUrl.searchParams.set('join', room_id);
    document.getElementById('lobby-share-link').value = shareUrl.toString();
    document.getElementById('room-id-display').innerText = room_id;
    const lobbyStatusEl = document.getElementById('lobby-status');
    if (player_color === 'white' || player_color === 'black') {
        const sideName = player_color === 'white' ? 'Blancs' : 'Noirs';
        lobbyStatusEl.innerText = `⏳ En attente de l'adversaire... (Vous jouez les ${sideName})`;
    } else {
        lobbyStatusEl.innerText = "⏳ En attente de l'adversaire...";
    }
    document.getElementById('lobby-area').classList.remove('hidden');

    ws = new WebSocket(`${WS_URL}/${game_room}/${player_color}`);
    ws.onmessage = (event) => {
        current_state = JSON.parse(event.data);
        if (
            (current_state.assigned_color === 'white' || current_state.assigned_color === 'black') &&
            player_color !== current_state.assigned_color
        ) {
            player_color = current_state.assigned_color;
            sessionStorage.setItem('chess_player_color', player_color);
            const sideName = player_color === 'white' ? 'Blancs' : 'Noirs';
            lobbyStatusEl.innerText = `⏳ En attente de l'adversaire... (Vous jouez les ${sideName})`;
            if (clashModeActive) {
                enterClashMode();
            }
        }
        const clashStarted = current_state.clash && current_state.clash.started;
        if (current_state.players_count >= 2 || clashStarted || current_state.status === 'game_over') {
            document.getElementById('lobby-area').classList.add('hidden');
            document.getElementById('game-area').classList.remove('hidden');
        }
        document.getElementById('variant-title').innerText = "Mode : " + (VARIANT_NAMES[current_state.variant] || current_state.variant);

        if (current_state.variant === 'clash_chess' && current_state.clash) {
            handleClashStateUpdate(current_state);
            return;
        }
        if (clashModeActive) {
            exitClashMode();
        }

        updateStatus();
        renderBoard();
    };
    ws.onclose = () => {
        document.getElementById('status-message').innerText = "Déconnecté. Rafraîchissez pour reconnecter.";
    };
}

function updateStatus() {
    if (current_state.status === 'game_over') {
        const go = document.getElementById('game-over-message');
        go.classList.remove('hidden');
        go.innerText = current_state.winner === 'draw' ? "Match Nul / Égalité parfaite !" : `Victoire du joueur : ${current_state.winner.toUpperCase()} !`;
        document.getElementById('status-message').innerText = "Partie terminée";
        document.getElementById('promotion-modal').classList.add('hidden');
        return;
    }
    
    if (current_state.status === 'awaiting_promotion') {
        if (current_state.turn === player_color) {
            document.querySelectorAll('.promo-btn').forEach(btn => {
                btn.innerHTML = getPieceSvgMarkup(btn.dataset.piece, player_color);
            });
            document.getElementById('promotion-modal').classList.remove('hidden');
            document.getElementById('status-message').innerText = "Choisissez votre promotion !";
        } else {
            document.getElementById('status-message').innerText = "L'adversaire choisit sa promotion...";
        }
        return;
    } else {
        document.getElementById('promotion-modal').classList.add('hidden');
    }
    
    const myTurn = current_state.turn === player_color;
    let msg = myTurn ? "C'est à vous de jouer" : "Tour de l'adversaire";
    
    if (current_state.variant === 'bataille') {
        if (!current_state.bataille_ready[player_color]) msg = "Phase de placement !";
        else if (!current_state.bataille_ready[player_color === 'white' ? 'black' : 'white']) msg = "Adversaire place ses pièces...";
    }
    if (current_state.variant === 'hidden_queen' && !current_state.hq_chosen) {
        msg = "Choisissez votre Dame Cachée !";
        document.getElementById('hidden-queen-overlay').classList.remove('hidden');
    } else {
        document.getElementById('hidden-queen-overlay').classList.add('hidden');
    }
    document.getElementById('status-message').innerText = msg;
}

function renderBoard() {
    const table = document.getElementById('chessboard');
    table.innerHTML = '';
    const isReversed = player_color === 'black';
    const isBataillePlacement =
        current_state.variant === 'bataille' &&
        current_state.bataille_ready &&
        !(current_state.bataille_ready.white && current_state.bataille_ready.black);

    for (let r = 0; r < 8; r++) {
        const rowData = isReversed ? 7 - r : r;
        const tr = document.createElement('tr');
        for (let c = 0; c < 8; c++) {
            const colData = isReversed ? 7 - c : c;
            const piece = current_state.board[rowData][colData];
            const td = document.createElement('td');
            td.className = ((rowData + colData) % 2 === 1) ? 'dark-square' : 'light-square';

            if (isBataillePlacement && r < 4) {
                td.classList.add('bataille-enemy-zone');
            }
            
            // Fog of war
            if (current_state.vision_map && !current_state.vision_map[rowData][colData]) {
                td.classList.add('fog-square');
            }
            
            // Highlight logic
            const keyStr = selected_pos ? (Array.isArray(selected_pos) ? `${selected_pos[0]},${selected_pos[1]}` : selected_pos) : null;
            if (keyStr && current_state.legal_moves && current_state.legal_moves[keyStr]) {
                const moves = current_state.legal_moves[keyStr];
                for (let m of moves) {
                    if (m.to[0] === rowData && m.to[1] === colData) {
                        td.classList.add(m.is_capture ? 'highlight-capture' : 'highlight-move');
                    }
                }
            }
            if (selected_pos && Array.isArray(selected_pos) && selected_pos[0] === rowData && selected_pos[1] === colData) {
                td.classList.add('selected');
            }

            td.dataset.r = rowData;
            td.dataset.c = colData;
            td.addEventListener('click', onSquareClick);

            if (piece) {
                const span = document.createElement('span');
                span.className = 'square-content';
                span.innerHTML = getPieceSvgMarkup(piece);
                
                // Show secret crown badge to the owner of the Hidden Queen
                if (current_state.variant === 'hidden_queen' && current_state.my_hidden_queen) {
                    const [hqr, hqc] = current_state.my_hidden_queen;
                    if (rowData === hqr && colData === hqc) {
                        const badge = document.createElement('span');
                        badge.innerText = '👑';
                        badge.style.position = 'absolute';
                        badge.style.top = '2px';
                        badge.style.right = '4px';
                        badge.style.fontSize = '0.9rem';
                        badge.style.zIndex = '5';
                        badge.style.pointerEvents = 'none';
                        td.appendChild(badge);
                    }
                }

                td.appendChild(span);
            }
            tr.appendChild(td);
        }
        table.appendChild(tr);
    }
    renderPockets();
}

function renderPockets() {
    const benchArea = document.getElementById('bataille-setup-area');
    if (current_state.variant === 'bataille' && !current_state.bataille_ready[player_color]) {
        benchArea.classList.remove('hidden');
        const bench = document.getElementById('bataille-bench');
        bench.innerHTML = '';
        current_state.bataille_bench.forEach((p, idx) => {
            const div = document.createElement('div');
            div.className = 'pocket-piece';
            div.innerHTML = getPieceSvgMarkup(p);
            if (selected_pos === `bench_${idx}`) div.classList.add('selected');
            div.onclick = () => {
                selected_pos = `bench_${idx}`;
                renderBoard();
            };
            bench.appendChild(div);
        });
    } else {
        benchArea.classList.add('hidden');
    }

    const playerPocket = document.getElementById('player-pocket');
    const oppPocket = document.getElementById('opponent-pocket');
    playerPocket.innerHTML = ''; oppPocket.innerHTML = '';
    
    if (current_state.pockets) {
        playerPocket.classList.remove('hidden'); 
        oppPocket.classList.remove('hidden');
        
        const oppColor = player_color === 'white' ? 'black' : 'white';
        
        current_state.pockets[player_color].forEach(p => {
            const div = document.createElement('div');
            div.className = 'pocket-piece';
            div.innerHTML = getPieceSvgMarkup(p);
            
            if (current_state.variant === 'clubhouse') {
                if (selected_pos === `drop_${p}`) div.classList.add('selected');
                div.onclick = () => {
                    if (current_state.turn === player_color && current_state.status === 'playing') {
                        selected_pos = `drop_${p}`;
                        renderBoard();
                    }
                };
            }
            playerPocket.appendChild(div);
        });
        
        current_state.pockets[oppColor].forEach(p => {
            const div = document.createElement('div');
            div.className = 'pocket-piece';
            div.innerHTML = getPieceSvgMarkup(p);
            oppPocket.appendChild(div);
        });
    }
}

function onSquareClick(e) {
    const r = parseInt(e.currentTarget.dataset.r);
    const c = parseInt(e.currentTarget.dataset.c);
    const piece = current_state.board[r][c];

    // Bataille setup phase
    if (current_state.variant === 'bataille' && !current_state.bataille_ready[player_color]) {
        const allowedRanks = player_color === 'white' ? [4, 5, 6, 7] : [0, 1, 2, 3];
        if (typeof selected_pos === 'string' && selected_pos.startsWith('bench_') && allowedRanks.includes(r)) {
            const idx = parseInt(selected_pos.split('_')[1]);
            if (piece) return;
            const p = current_state.bataille_bench[idx];
            current_state.board[r][c] = p;
            current_state.bataille_bench.splice(idx, 1);
            selected_pos = null;
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'bataille_place', board: current_state.board, bench: current_state.bataille_bench }));
            }
            renderBoard();
        } else if (piece && allowedRanks.includes(r) && ((player_color === 'white' && piece === piece.toUpperCase()) || (player_color === 'black' && piece === piece.toLowerCase()))) {
            current_state.bataille_bench.push(piece);
            current_state.board[r][c] = '';
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'bataille_place', board: current_state.board, bench: current_state.bataille_bench }));
            }
            renderBoard();
        }
        return;
    }

    // Hidden Queen setup phase
    if (current_state.variant === 'hidden_queen' && !current_state.hq_chosen) {
        if (piece && piece.toLowerCase() === 'p' && ((player_color === 'white' && piece === piece.toUpperCase()) || (player_color === 'black' && piece === piece.toLowerCase()))) {
            if (confirm("Désigner ce pion comme votre Dame Cachée secrète ?")) {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'hidden_queen_setup', pos: [r, c] }));
                }
            }
        }
        return;
    }

    if (current_state.turn !== player_color || current_state.status !== 'playing') return;

    if (selected_pos) {
        const keyStr = Array.isArray(selected_pos) ? `${selected_pos[0]},${selected_pos[1]}` : selected_pos;
        let moveFound = null;
        if (current_state.legal_moves && current_state.legal_moves[keyStr]) {
            for (let m of current_state.legal_moves[keyStr]) {
                if (m.to[0] === r && m.to[1] === c) {
                    moveFound = m;
                    break;
                }
            }
        }

        if (moveFound) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'move', move: moveFound }));
            }
            selected_pos = null;
            return;
        }

        if (piece && ((player_color === 'white' && piece === piece.toUpperCase()) || (player_color === 'black' && piece === piece.toLowerCase()))) {
            selected_pos = [r, c];
            renderBoard();
        } else {
            selected_pos = null;
            renderBoard();
        }
    } else {
        if (piece && ((player_color === 'white' && piece === piece.toUpperCase()) || (player_color === 'black' && piece === piece.toLowerCase()))) {
            selected_pos = [r, c];
            renderBoard();
        }
    }
}

/* =========================================================================
   CLASH CHESS — REAL-TIME RENDERER (60 FPS), DECK DRAG & DROP, FX
   ========================================================================= */

function initClashUI() {
    document.querySelectorAll('.clash-promo-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            if (!clashModeActive || !clashSnapshot || !clashSnapshot.pending_promotions.length) return;
            const pending = clashSnapshot.pending_promotions[0];
            const chosen = e.currentTarget.dataset.piece;
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'clash_promote',
                    piece_id: pending.piece_id,
                    piece: chosen
                }));
            }
        });
    });

    document.querySelectorAll('.clash-deck-card').forEach(card => {
        card.addEventListener('pointerdown', onClashDeckPointerDown);
    });

    window.addEventListener('pointermove', onClashDeckPointerMove);
    window.addEventListener('pointerup', onClashDeckPointerUp);
    window.addEventListener('pointercancel', onClashDeckPointerCancel);
    window.addEventListener('keydown', onClashKeyDown);
    window.addEventListener('contextmenu', onClashContextMenu);
}

function cancelClashSelection() {
    if (clashDragState) {
        document.getElementById('clash-drag-ghost').classList.add('hidden');
        clearClashDropHover();
        clashDragState = null;
    }
    selectedClashDeckPiece = null;
    selectedClashPieceId = null;
    const previewEl = document.getElementById('clash-hover-preview');
    if (previewEl) previewEl.classList.add('hidden');
    if (clashSnapshot && clashSnapshot.started && current_state && current_state.status === 'playing') {
        document.getElementById('status-message').innerText = "Temps réel — Invoquez et déplacez librement !";
    }
    refreshClashBoardHighlights();
}

function onClashKeyDown(e) {
    if (!clashModeActive || !clashSnapshot || !clashSnapshot.started || !current_state || current_state.status !== 'playing') {
        return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = e.target && e.target.tagName ? e.target.tagName.toUpperCase() : '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    if (e.key === 'Escape') {
        e.preventDefault();
        cancelClashSelection();
        return;
    }

    const key = e.key.toLowerCase();
    const pieceType = CLASH_AZERTY_SHORTCUTS[key];
    if (!pieceType) return;

    e.preventDefault();
    const cost = CLASH_SPAWN_COSTS[pieceType] || 99;
    // Insensitive to keyboard shortcut when energy is insufficient.
    if (getLiveClashEnergy() + 1e-6 < cost) {
        return;
    }

    selectedClashPieceId = null;
    selectedClashDeckPiece = (selectedClashDeckPiece === pieceType) ? null : pieceType;
    const statusEl = document.getElementById('status-message');
    if (selectedClashDeckPiece) {
        statusEl.innerText = "Cliquez une case vide dans votre moitié de terrain (Échap / clic droit pour annuler)";
    } else {
        statusEl.innerText = "Temps réel — Invoquez et déplacez librement !";
    }
    refreshClashBoardHighlights();
}

function onClashContextMenu(e) {
    if (!clashModeActive) return;
    if (selectedClashDeckPiece || selectedClashPieceId || clashDragState) {
        e.preventDefault();
        cancelClashSelection();
    }
}

function enterClashMode() {
    clashModeActive = true;
    selectedClashDeckPiece = null;
    selectedClashPieceId = null;
    clashDragState = null;
    clashHoveredSquare = null;
    clashHoverPreviewKey = '';
    clashEnergyLastWhole = null;
    clashEnergySparks = [];
    clashCardWasAffordable = { p: null, n: null, b: null, r: null, q: null };
    seenClashEventIds.clear();
    clashParticles = [];
    clashShockwaves = [];

    document.getElementById('app-container').classList.add('clash-mode');
    document.getElementById('clash-hud').classList.remove('hidden');
    document.getElementById('clash-pieces-layer').classList.remove('hidden');
    document.getElementById('clash-hover-layer').classList.remove('hidden');
    document.getElementById('clash-hover-preview').classList.add('hidden');
    document.getElementById('clash-fx-canvas').classList.remove('hidden');
    document.getElementById('clash-controls-panel').classList.remove('hidden');
    document.getElementById('opponent-pocket').classList.add('hidden');
    document.getElementById('player-pocket').classList.add('hidden');
    document.getElementById('bataille-setup-area').classList.add('hidden');
    document.getElementById('hidden-queen-overlay').classList.add('hidden');
    document.getElementById('promotion-modal').classList.add('hidden');
    document.getElementById('game-over-message').classList.add('hidden');

    // Build static 8x8 board grid once so piece DOM animations stay silky at 60 FPS.
    const table = document.getElementById('chessboard');
    table.innerHTML = '';
    table.onpointerleave = () => {
        clashHoveredSquare = null;
        updateClashHoverPreview();
    };
    clashBoardCells = Array.from({ length: 8 }, () => new Array(8));
    const isReversed = player_color === 'black';

    for (let r = 0; r < 8; r++) {
        const rowData = isReversed ? 7 - r : r;
        const tr = document.createElement('tr');
        for (let c = 0; c < 8; c++) {
            const colData = isReversed ? 7 - c : c;
            const td = document.createElement('td');
            td.className = ((rowData + colData) % 2 === 1) ? 'dark-square' : 'light-square';
            td.dataset.r = rowData;
            td.dataset.c = colData;
            td.addEventListener('click', onClashSquareClick);
            td.addEventListener('pointerenter', () => {
                clashHoveredSquare = { row: rowData, col: colData };
                updateClashHoverPreview();
            });
            clashBoardCells[rowData][colData] = td;
            tr.appendChild(td);
        }
        table.appendChild(tr);
    }

    // Build 20 distinct energy segments once.
    const segContainer = document.getElementById('clash-energy-segments');
    segContainer.innerHTML = '';
    clashEnergySegNodes = [];
    for (let i = 0; i < 20; i++) {
        const seg = document.createElement('div');
        seg.className = 'clash-energy-seg';
        const fill = document.createElement('div');
        fill.className = 'clash-energy-seg-fill';
        seg.appendChild(fill);
        segContainer.appendChild(seg);
        clashEnergySegNodes.push({ seg, fill });
    }

    // Color deck & promotion glyphs to match player color.
    document.querySelectorAll('.clash-deck-card').forEach(card => {
        const pType = card.dataset.piece;
        const glyphEl = card.querySelector('.clash-card-glyph');
        glyphEl.innerHTML = getPieceSvgMarkup(pType, player_color);
        card.classList.remove('card-unlock-pulse');
    });

    document.querySelectorAll('.clash-promo-btn').forEach(btn => {
        btn.innerHTML = getPieceSvgMarkup(btn.dataset.piece, player_color);
    });

    const layer = document.getElementById('clash-pieces-layer');
    layer.innerHTML = '';
    clashPieceNodes.clear();
    clashTargetNodes.clear();

    resizeClashCanvas();
    resizeClashEnergyCanvas();
    clashLastFrameTime = performance.now();
    if (!clashAnimFrameId) {
        clashAnimFrameId = requestAnimationFrame(clashRenderLoop);
    }
}

function exitClashMode() {
    clashModeActive = false;
    if (clashAnimFrameId) {
        cancelAnimationFrame(clashAnimFrameId);
        clashAnimFrameId = null;
    }
    clashSnapshot = null;
    clashPieceNodes.clear();
    clashTargetNodes.clear();
    clashEnergySegNodes = [];
    clashEnergyLastWhole = null;
    clashEnergySparks = [];
    clashHoveredSquare = null;
    clashHoverPreviewKey = '';
    clashParticles = [];
    clashShockwaves = [];
    seenClashEventIds.clear();
    selectedClashDeckPiece = null;
    selectedClashPieceId = null;
    clashDragState = null;

    document.getElementById('app-container').classList.remove('clash-mode');
    document.getElementById('clash-hud').classList.add('hidden');
    document.getElementById('clash-pieces-layer').classList.add('hidden');
    document.getElementById('clash-pieces-layer').innerHTML = '';
    document.getElementById('clash-hover-layer').classList.add('hidden');
    document.getElementById('clash-hover-preview').classList.add('hidden');
    document.getElementById('clash-fx-canvas').classList.add('hidden');
    document.getElementById('clash-promotion-bar').classList.add('hidden');
    document.getElementById('clash-controls-panel').classList.add('hidden');
    document.getElementById('clash-drag-ghost').classList.add('hidden');
}

function resizeClashEnergyCanvas() {
    const canvas = document.getElementById('clash-energy-fx-canvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
        const w = Math.round(rect.width);
        const h = Math.round(rect.height);
        if (canvas.width !== w || canvas.height !== h) {
            canvas.width = w;
            canvas.height = h;
        }
    }
}

function resizeClashCanvas() {
    const canvas = document.getElementById('clash-fx-canvas');
    const rect = canvas.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
        if (canvas.width !== Math.round(rect.width) || canvas.height !== Math.round(rect.height)) {
            canvas.width = Math.round(rect.width);
            canvas.height = Math.round(rect.height);
        }
    }
}

function formatClashClock(seconds) {
    const clamped = Math.max(0, Math.ceil(seconds));
    const mins = Math.floor(clamped / 60);
    const secs = clamped % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function getLiveClashEnergy() {
    if (!clashSnapshot) return 0;
    if (!clashSnapshot.started || !current_state || current_state.status !== 'playing') {
        return clashSnapshot.my_energy;
    }
    const dtSec = Math.min(Math.max(0, (performance.now() - clashSnapshotTime) / 1000), 0.08);
    const rate = CLASH_ENERGY_RATES[clashSnapshot.energy_multiplier] || 0.5;
    return Math.min(clashSnapshot.max_energy, clashSnapshot.my_energy + rate * dtSec);
}

function handleClashStateUpdate(state) {
    if (!clashModeActive) {
        enterClashMode();
    }
    clashSnapshot = state.clash;
    clashSnapshotTime = performance.now();

    // Trigger canvas particle bursts & board shake for new server events.
    if (Array.isArray(clashSnapshot.events)) {
        for (const ev of clashSnapshot.events) {
            if (!seenClashEventIds.has(ev.id)) {
                seenClashEventIds.add(ev.id);
                triggerClashEventFX(ev);
            }
        }
        if (seenClashEventIds.size > 400) {
            const activeIds = new Set(clashSnapshot.events.map(e => e.id));
            seenClashEventIds = activeIds;
        }
    }

    // Update HUD: timer, multiplier, material scores.
    document.getElementById('clash-timer').innerText = formatClashClock(clashSnapshot.time_remaining);
    const mult = clashSnapshot.energy_multiplier || 1;
    const multBadge = document.getElementById('clash-multiplier-badge');
    multBadge.innerText = `×${mult}`;
    multBadge.className = `mult-${mult}`;

    const energyBar = document.getElementById('clash-energy-bar');
    energyBar.className = `mult-${mult}`;
    document.getElementById('clash-energy-rate-label').innerText = CLASH_RATE_LABELS[mult] || CLASH_RATE_LABELS[1];

    document.getElementById('clash-score-white').innerText = clashSnapshot.scores ? clashSnapshot.scores.white : 0;
    document.getElementById('clash-score-black').innerText = clashSnapshot.scores ? clashSnapshot.scores.black : 0;

    // Non-blocking free promotion bar.
    const promoBar = document.getElementById('clash-promotion-bar');
    if (state.status === 'playing' && clashSnapshot.pending_promotions && clashSnapshot.pending_promotions.length > 0) {
        promoBar.classList.remove('hidden');
    } else {
        promoBar.classList.add('hidden');
    }

    // Status & game-over messages.
    const goEl = document.getElementById('game-over-message');
    const statusEl = document.getElementById('status-message');
    if (state.status === 'game_over') {
        selectedClashDeckPiece = null;
        selectedClashPieceId = null;
        goEl.classList.remove('hidden');
        const winnerLabel = state.winner === 'white' ? 'BLANCS' : (state.winner === 'black' ? 'NOIRS' : 'ÉGALITÉ');
        const wPts = clashSnapshot.scores ? clashSnapshot.scores.white : 0;
        const bPts = clashSnapshot.scores ? clashSnapshot.scores.black : 0;
        if (clashSnapshot.win_reason === 'double_king_capture') {
            goEl.innerText = "Égalité ! Les deux Rois ont été détruits sur le même tick !";
        } else if (clashSnapshot.win_reason === 'king_captured') {
            goEl.innerText = `Victoire des ${winnerLabel} — Roi adverse détruit !`;
        } else if (clashSnapshot.win_reason === 'timeout_material') {
            goEl.innerText = `Fin du chrono (5:00) — Victoire aux points (${wPts} vs ${bPts}) : ${winnerLabel} !`;
        } else if (clashSnapshot.win_reason === 'timeout_draw') {
            goEl.innerText = `Fin du chrono (5:00) — Égalité parfaite aux points (${wPts} - ${bPts}) !`;
        } else if (clashSnapshot.win_reason === 'resign') {
            goEl.innerText = `Victoire des ${winnerLabel} par abandon !`;
        } else {
            goEl.innerText = state.winner === 'draw' ? "Match Nul !" : `Victoire des ${winnerLabel} !`;
        }
        statusEl.innerText = "Partie terminée";
    } else {
        goEl.classList.add('hidden');
        if (!clashSnapshot.started) {
            statusEl.innerText = "En attente du second joueur...";
        } else if (selectedClashDeckPiece) {
            statusEl.innerText = "Cliquez une case vide dans votre moitié de terrain";
        } else {
            statusEl.innerText = "Temps réel — Invoquez et déplacez librement !";
        }
    }

    // Validate currently selected board piece.
    if (selectedClashPieceId) {
        const sel = clashSnapshot.pieces.find(p => p.id === selectedClashPieceId);
        if (!sel || sel.state !== 'ACTIVE' || sel.color !== player_color) {
            selectedClashPieceId = null;
        }
    }

    refreshClashBoardHighlights();
}

function triggerClashShake() {
    const container = document.getElementById('board-container');
    container.classList.remove('board-shake');
    void container.offsetWidth;
    container.classList.add('board-shake');
}

function spawnBurst(bx, by, colorHex, count, speed = 2.6) {
    for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.4;
        const spd = speed * (0.45 + Math.random() * 0.85);
        clashParticles.push({
            bx,
            by,
            vx: Math.cos(angle) * spd,
            vy: Math.sin(angle) * spd,
            life: 0,
            maxLife: 0.35 + Math.random() * 0.25,
            size: 2.5 + Math.random() * 3.5,
            color: colorHex
        });
    }
}

function triggerClashEventFX(ev) {
    if (ev.kind === 'spawn') {
        const bx = ev.col + 0.5;
        const by = ev.row + 0.5;
        const color = ev.color === 'white' ? '#38bdf8' : '#a855f7';
        spawnBurst(bx, by, color, 14, 2.2);
        clashShockwaves.push({ bx, by, life: 0, maxLife: 0.38, maxRadius: 0.65, color });
    } else if (ev.kind === 'collision') {
        const bx = ev.x + 0.5;
        const by = ev.y + 0.5;
        triggerClashShake();
        if (ev.outcome === 'king_captured') {
            spawnBurst(bx, by, '#facc15', 30, 4.2);
            spawnBurst(bx, by, '#f43f5e', 20, 3.0);
            clashShockwaves.push({ bx, by, life: 0, maxLife: 0.55, maxRadius: 1.4, color: '#facc15' });
        } else if (ev.outcome === 'mutual') {
            spawnBurst(bx, by, '#f43f5e', 22, 3.4);
            spawnBurst(bx, by, '#38bdf8', 14, 2.6);
            clashShockwaves.push({ bx, by, life: 0, maxLife: 0.42, maxRadius: 0.95, color: '#f43f5e' });
        } else {
            const color = ev.winner_color === 'white' ? '#38bdf8' : '#c084fc';
            spawnBurst(bx, by, color, 18, 3.0);
            clashShockwaves.push({ bx, by, life: 0, maxLife: 0.36, maxRadius: 0.8, color });
        }
    } else if (ev.kind === 'promote') {
        const bx = ev.col + 0.5;
        const by = ev.row + 0.5;
        spawnBurst(bx, by, '#facc15', 22, 3.1);
        clashShockwaves.push({ bx, by, life: 0, maxLife: 0.45, maxRadius: 0.9, color: '#facc15' });
    }
}

function isInOwnSpawnHalf(row) {
    if (player_color === 'white') return row >= 4 && row <= 7;
    if (player_color === 'black') return row >= 0 && row <= 3;
    return false;
}

function isClashSquareEmptyForSpawn(row, col) {
    if (!clashSnapshot) return false;
    for (const p of clashSnapshot.pieces) {
        if (p.state !== 'MOVING') {
            if (p.row === row && p.col === col) return false;
        } else {
            if (p.color === player_color && p.target && p.target[0] === row && p.target[1] === col) {
                return false;
            }
            if (!p.is_airborne) {
                if (Math.hypot(p.x - col, p.y - row) <= 0.45) return false;
                if (Math.round(p.x) === col && Math.round(p.y) === row) return false;
            }
        }
    }
    return true;
}

function getClientClashLegalTargets(piece) {
    if (!piece || !clashSnapshot || piece.state !== 'ACTIVE') return [];
    const sr = piece.row;
    const sc = piece.col;
    const color = piece.color;
    const pType = piece.type;
    const targets = [];

    const hasStationaryFriendly = (r, c) => {
        for (const other of clashSnapshot.pieces) {
            if (other.id !== piece.id && other.color === color && other.state !== 'MOVING' && other.row === r && other.col === c) {
                return true;
            }
        }
        return false;
    };

    const hasFriendlyBlock = (r, c) => {
        for (const other of clashSnapshot.pieces) {
            if (other.id === piece.id || other.color !== color) continue;
            if (other.state !== 'MOVING') {
                if (other.row === r && other.col === c) return true;
            } else if (other.target && other.target[0] === r && other.target[1] === c) {
                return true;
            }
        }
        return false;
    };

    const hasStationaryEnemy = (r, c) => {
        for (const other of clashSnapshot.pieces) {
            if (other.color !== color && other.state !== 'MOVING' && other.row === r && other.col === c) {
                return true;
            }
        }
        return false;
    };

    const hasGroundedEnemyAt = (r, c) => {
        for (const other of clashSnapshot.pieces) {
            if (other.color === color || other.is_airborne) continue;
            if (other.state !== 'MOVING') {
                if (other.row === r && other.col === c) return true;
            } else if (Math.abs(other.x - c) <= 0.55 && Math.abs(other.y - r) <= 0.55) {
                return true;
            }
        }
        return false;
    };

    if (pType === 'k') {
        for (let dr = -1; dr <= 1; dr++) {
            for (let dc = -1; dc <= 1; dc++) {
                if (dr === 0 && dc === 0) continue;
                const nr = sr + dr;
                const nc = sc + dc;
                if (nr >= 0 && nr < 8 && nc >= 0 && nc < 8 && !hasFriendlyBlock(nr, nc)) {
                    targets.push({ row: nr, col: nc, isCapture: hasGroundedEnemyAt(nr, nc) });
                }
            }
        }
        return targets;
    }

    if (pType === 'n') {
        const jumps = [[-2,-1],[-2,1],[-1,-2],[-1,2],[1,-2],[1,2],[2,-1],[2,1]];
        for (const [dr, dc] of jumps) {
            const nr = sr + dr;
            const nc = sc + dc;
            if (nr >= 0 && nr < 8 && nc >= 0 && nc < 8 && !hasFriendlyBlock(nr, nc)) {
                targets.push({ row: nr, col: nc, isCapture: hasGroundedEnemyAt(nr, nc) });
            }
        }
        return targets;
    }

    if (pType === 'r' || pType === 'b' || pType === 'q') {
        const dirs = [];
        if (pType === 'r' || pType === 'q') dirs.push([-1,0],[1,0],[0,-1],[0,1]);
        if (pType === 'b' || pType === 'q') dirs.push([-1,-1],[-1,1],[1,-1],[1,1]);
        for (const [dr, dc] of dirs) {
            for (let step = 1; step < 8; step++) {
                const nr = sr + dr * step;
                const nc = sc + dc * step;
                if (nr < 0 || nr >= 8 || nc < 0 || nc >= 8) break;
                if (hasStationaryFriendly(nr, nc)) break;
                const enemyStop = hasStationaryEnemy(nr, nc);
                if (!hasFriendlyBlock(nr, nc)) {
                    targets.push({ row: nr, col: nc, isCapture: enemyStop || hasGroundedEnemyAt(nr, nc) });
                }
                if (enemyStop) break;
            }
        }
        return targets;
    }

    if (pType === 'p') {
        const forward = color === 'white' ? -1 : 1;
        const startRow = color === 'white' ? 6 : 1;
        const r1 = sr + forward;
        if (r1 >= 0 && r1 < 8) {
            if (!hasStationaryEnemy(r1, sc) && !hasFriendlyBlock(r1, sc)) {
                targets.push({ row: r1, col: sc, isCapture: false });
            }
            if (sr === startRow) {
                const r2 = sr + 2 * forward;
                if (
                    r2 >= 0 && r2 < 8 &&
                    !hasStationaryEnemy(r1, sc) &&
                    !hasStationaryFriendly(r1, sc) &&
                    !hasStationaryEnemy(r2, sc) &&
                    !hasFriendlyBlock(r2, sc)
                ) {
                    targets.push({ row: r2, col: sc, isCapture: false });
                }
            }
            for (const dc of [-1, 1]) {
                const nc = sc + dc;
                if (nc >= 0 && nc < 8 && !hasFriendlyBlock(r1, nc) && hasGroundedEnemyAt(r1, nc)) {
                    targets.push({ row: r1, col: nc, isCapture: true });
                }
            }
        }
    }
    return targets;
}

function updateClashHoverPreview() {
    if (!clashModeActive || !clashBoardCells.length) return;
    if (!(clashDragState && clashDragState.dragging)) {
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                clashBoardCells[r][c].classList.remove('clash-drop-hover');
            }
        }
    }

    const previewEl = document.getElementById('clash-hover-preview');
    if (!previewEl) return;

    if (
        selectedClashDeckPiece &&
        !(clashDragState && clashDragState.dragging) &&
        clashHoveredSquare &&
        clashSnapshot &&
        clashSnapshot.started &&
        current_state &&
        current_state.status === 'playing'
    ) {
        const { row, col } = clashHoveredSquare;
        const cost = CLASH_SPAWN_COSTS[selectedClashDeckPiece] || 99;
        if (
            isInOwnSpawnHalf(row) &&
            isClashSquareEmptyForSpawn(row, col) &&
            getLiveClashEnergy() + 1e-6 >= cost
        ) {
            const key = `${player_color}_${selectedClashDeckPiece}`;
            if (clashHoverPreviewKey !== key) {
                previewEl.innerHTML = getPieceSvgMarkup(selectedClashDeckPiece, player_color);
                clashHoverPreviewKey = key;
            }
            const isReversed = player_color === 'black';
            const vx = isReversed ? 7 - col : col;
            const vy = isReversed ? 7 - row : row;
            previewEl.style.transform = `translate3d(${vx * 100}%, ${vy * 100}%, 0)`;
            previewEl.classList.remove('hidden');
            if (clashBoardCells[row] && clashBoardCells[row][col]) {
                clashBoardCells[row][col].classList.add('clash-drop-hover');
            }
            return;
        }
    }

    previewEl.classList.add('hidden');
}

function refreshClashBoardHighlights() {
    if (!clashModeActive || !clashBoardCells.length) return;
    for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
            const td = clashBoardCells[r][c];
            td.classList.remove('selected', 'highlight-move', 'highlight-capture', 'clash-spawn-zone', 'clash-spawn-valid');
        }
    }

    if (!clashSnapshot || !current_state || current_state.status !== 'playing' || !clashSnapshot.started) {
        updateClashHoverPreview();
        return;
    }

    const showSpawn = selectedClashDeckPiece || (clashDragState && clashDragState.dragging);
    if (showSpawn) {
        for (let r = 0; r < 8; r++) {
            if (!isInOwnSpawnHalf(r)) continue;
            for (let c = 0; c < 8; c++) {
                const td = clashBoardCells[r][c];
                td.classList.add('clash-spawn-zone');
                if (isClashSquareEmptyForSpawn(r, c)) {
                    td.classList.add('clash-spawn-valid');
                }
            }
        }
        updateClashHoverPreview();
        return;
    }

    if (selectedClashPieceId) {
        const piece = clashSnapshot.pieces.find(p => p.id === selectedClashPieceId);
        if (piece && piece.state === 'ACTIVE') {
            clashBoardCells[piece.row][piece.col].classList.add('selected');
            const targets = getClientClashLegalTargets(piece);
            for (const t of targets) {
                clashBoardCells[t.row][t.col].classList.add(t.isCapture ? 'highlight-capture' : 'highlight-move');
            }
        }
    }
    updateClashHoverPreview();
}

function createClashPieceNode(p) {
    const root = document.createElement('div');
    root.className = 'clash-piece';

    const shadow = document.createElement('div');
    shadow.className = 'clash-jump-shadow';

    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('class', 'clash-ring');
    svg.setAttribute('viewBox', '0 0 100 100');

    const bgCircle = document.createElementNS(svgNS, 'circle');
    bgCircle.setAttribute('class', 'clash-ring-bg');
    bgCircle.setAttribute('cx', '50');
    bgCircle.setAttribute('cy', '50');
    bgCircle.setAttribute('r', '42');

    const fgCircle = document.createElementNS(svgNS, 'circle');
    fgCircle.setAttribute('class', 'clash-ring-fg');
    fgCircle.setAttribute('cx', '50');
    fgCircle.setAttribute('cy', '50');
    fgCircle.setAttribute('r', '42');
    fgCircle.style.strokeDasharray = `${CLASH_RING_CIRCUMFERENCE}`;

    svg.appendChild(bgCircle);
    svg.appendChild(fgCircle);

    const glyph = document.createElement('span');
    glyph.className = 'clash-piece-glyph';
    const pieceKey = `${p.color}_${p.type}`;
    glyph.innerHTML = getPieceSvgMarkup(p.type, p.color);

    const timerBadge = document.createElement('span');
    timerBadge.className = 'clash-timer-badge hidden';

    root.appendChild(shadow);
    root.appendChild(svg);
    root.appendChild(glyph);
    root.appendChild(timerBadge);

    document.getElementById('clash-pieces-layer').appendChild(root);
    return { root, shadow, svg, fgCircle, glyph, timerBadge, pieceKey };
}

function spawnEnergyImpactSparks(segIndex, mult) {
    const canvas = document.getElementById('clash-energy-fx-canvas');
    if (!canvas || canvas.width === 0 || canvas.height === 0) return;
    const padX = 8;
    const usableW = Math.max(1, canvas.width - padX * 2);
    const x = padX + ((segIndex + 0.92) / 20) * usableW;
    const y = canvas.height * 0.5;
    const count = mult >= 3 ? 16 : (mult === 2 ? 12 : 8);
    const palette = mult >= 3
        ? ['#ffffff', '#fef08a', '#f59e0b', '#fb7185']
        : (mult === 2 ? ['#ffffff', '#fef08a', '#e879f9', '#38bdf8'] : ['#ffffff', '#fef08a', '#7dd3fc']);

    for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.5;
        const speed = (28 + Math.random() * 54) * (1 + (mult - 1) * 0.25);
        clashEnergySparks.push({
            x,
            y,
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed,
            life: 0,
            maxLife: 0.22 + Math.random() * 0.16,
            size: 1.5 + Math.random() * 2.2,
            color: palette[i % palette.length]
        });
    }
}

function drawElectricArc(ctx, x1, y1, x2, y2, jitter, color, lineWidth) {
    const segments = 5;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    for (let i = 1; i < segments; i++) {
        const t = i / segments;
        const px = x1 + (x2 - x1) * t + (Math.random() - 0.5) * jitter;
        const py = y1 + (y2 - y1) * t + (Math.random() - 0.5) * jitter;
        ctx.lineTo(px, py);
    }
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.restore();
}

function renderClashEnergyFx(dt, liveEnergy, maxEnergy, mult, isPrecharging, isPlaying) {
    resizeClashEnergyCanvas();
    const canvas = document.getElementById('clash-energy-fx-canvas');
    if (!canvas || canvas.width === 0 || canvas.height === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const padX = 8;
    const padY = 10;
    const usableW = Math.max(1, canvas.width - padX * 2);
    const barTop = padY;
    const barBottom = canvas.height - padY;
    const barMid = canvas.height * 0.5;
    const edgeX = padX + (liveEnergy / maxEnergy) * usableW;

    // 1. Pre-charge static electricity arcs crackling on the charging leading edge (0.2s-0.3s before +1).
    if (isPlaying && liveEnergy < maxEnergy) {
        const showAmbientOverdrive = mult >= 2 && Math.random() < (mult === 3 ? 0.65 : 0.35);
        if (isPrecharging || showAmbientOverdrive) {
            const arcCount = isPrecharging
                ? (mult >= 3 ? 6 : (mult === 2 ? 4 : 2))
                : (mult >= 3 ? 3 : 1);
            const jitter = isPrecharging ? (5 + mult * 2.5) : (3 + mult * 1.5);
            const mainColor = mult >= 3 ? '#fef08a' : (mult === 2 ? '#e879f9' : '#7dd3fc');
            const coreColor = '#ffffff';

            for (let i = 0; i < arcCount; i++) {
                const startY = barTop + Math.random() * (barBottom - barTop);
                const endX = edgeX + (Math.random() - 0.3) * (10 + mult * 4);
                const endY = barTop - 3 + Math.random() * (barBottom - barTop + 6);
                drawElectricArc(ctx, edgeX, startY, endX, endY, jitter, mainColor, 1.8 + mult * 0.2);
                if (isPrecharging && i % 2 === 0) {
                    drawElectricArc(ctx, edgeX, startY, endX, endY, jitter * 0.6, coreColor, 0.9);
                }
            }

            // Emit tiny crackling micro-sparks on the leading edge during pre-charge.
            if (isPrecharging && Math.random() < 0.45 * mult) {
                clashEnergySparks.push({
                    x: edgeX,
                    y: barMid + (Math.random() - 0.5) * (barBottom - barTop),
                    vx: (Math.random() - 0.3) * 35,
                    vy: (Math.random() - 0.5) * 45,
                    life: 0,
                    maxLife: 0.14 + Math.random() * 0.1,
                    size: 1.2 + Math.random() * 1.4,
                    color: mult >= 3 ? '#fef08a' : '#e0f2fe'
                });
            }
        }
    }

    // 2. Render & advance impact / static sparks.
    for (let i = clashEnergySparks.length - 1; i >= 0; i--) {
        const sp = clashEnergySparks[i];
        sp.life += dt;
        if (sp.life >= sp.maxLife) {
            clashEnergySparks.splice(i, 1);
            continue;
        }
        sp.x += sp.vx * dt;
        sp.y += sp.vy * dt;
        const alpha = 1 - sp.life / sp.maxLife;
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = sp.color;
        ctx.shadowColor = sp.color;
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, sp.size * (0.4 + 0.6 * alpha), 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }
}

function clashRenderLoop(now) {
    if (!clashModeActive) return;

    const frameDt = Math.min(Math.max(0, (now - clashLastFrameTime) / 1000), 0.05);
    clashLastFrameTime = now;

    if (clashSnapshot) {
        const isPlaying = current_state && current_state.status === 'playing' && clashSnapshot.started;
        const dtSec = isPlaying ? Math.min(Math.max(0, (now - clashSnapshotTime) / 1000), 0.08) : 0;

        // 1. Smooth 20-segment energy bar, pre-charge static electricity & +1 impact pop.
        const mult = clashSnapshot.energy_multiplier || 1;
        const rate = CLASH_ENERGY_RATES[mult] || 0.5;
        const maxEnergy = clashSnapshot.max_energy || 20;
        const liveEnergy = Math.min(
            maxEnergy,
            clashSnapshot.my_energy + (isPlaying ? rate * dtSec : 0)
        );
        const wholeEnergy = Math.floor(liveEnergy + 1e-6);
        const fracEnergy = Math.max(0, Math.min(1, liveEnergy - wholeEnergy));

        if (clashEnergyLastWhole === null) {
            clashEnergyLastWhole = wholeEnergy;
        } else if (isPlaying && wholeEnergy > clashEnergyLastWhole) {
            for (let idx = clashEnergyLastWhole; idx < Math.min(20, wholeEnergy); idx++) {
                const segNode = clashEnergySegNodes[idx];
                if (segNode) {
                    segNode.seg.classList.remove('seg-impact-pop');
                    void segNode.seg.offsetWidth;
                    segNode.seg.classList.add('seg-impact-pop');
                }
                spawnEnergyImpactSparks(idx, mult);
            }
            clashEnergyLastWhole = wholeEnergy;
        } else if (wholeEnergy < clashEnergyLastWhole) {
            clashEnergyLastWhole = wholeEnergy;
        }

        const timeToNextUnit = (isPlaying && liveEnergy < maxEnergy - 1e-6)
            ? ((1.0 - fracEnergy) / rate)
            : Infinity;
        const isPrecharging = timeToNextUnit <= CLASH_PRECHARGE_WINDOW_SEC;

        for (let i = 0; i < clashEnergySegNodes.length; i++) {
            const { seg, fill } = clashEnergySegNodes[i];
            if (i < wholeEnergy) {
                fill.style.width = '100%';
                seg.classList.add('seg-filled');
                seg.classList.remove('seg-charging', 'seg-precharge');
            } else if (i === wholeEnergy && liveEnergy < maxEnergy) {
                fill.style.width = `${fracEnergy * 100}%`;
                seg.classList.remove('seg-filled');
                seg.classList.add('seg-charging');
                seg.classList.toggle('seg-precharge', isPrecharging);
            } else {
                fill.style.width = '0%';
                seg.classList.remove('seg-filled', 'seg-charging', 'seg-precharge');
            }
        }

        document.getElementById('clash-energy-label').innerText = `ÉNERGIE : ${wholeEnergy} / ${maxEnergy}`;
        renderClashEnergyFx(frameDt, liveEnergy, maxEnergy, mult, isPrecharging, isPlaying);

        // 2. Deck card affordability, unlock glow pulse & auto-cancel if energy drops below selected cost.
        document.querySelectorAll('.clash-deck-card').forEach(card => {
            const pType = card.dataset.piece;
            const cost = CLASH_SPAWN_COSTS[pType] || 99;
            const affordable = isPlaying && liveEnergy + 1e-6 >= cost;
            if (clashCardWasAffordable[pType] === false && affordable) {
                card.classList.remove('card-unlock-pulse');
                void card.offsetWidth;
                card.classList.add('card-unlock-pulse');
            }
            clashCardWasAffordable[pType] = affordable;
            card.classList.toggle('unaffordable', !affordable);
            card.classList.toggle('selected', selectedClashDeckPiece === pType);
        });

        if (selectedClashDeckPiece && isPlaying) {
            const selCost = CLASH_SPAWN_COSTS[selectedClashDeckPiece] || 99;
            if (liveEnergy + 1e-6 < selCost) {
                selectedClashDeckPiece = null;
                refreshClashBoardHighlights();
            }
        }

        // 3. Smoothly extrapolate and render all active pieces + own moving targets.
        const layer = document.getElementById('clash-pieces-layer');
        const isReversed = player_color === 'black';
        const seenPieces = new Set();
        const seenTargets = new Set();

        for (const p of clashSnapshot.pieces) {
            seenPieces.add(p.id);
            let node = clashPieceNodes.get(p.id);
            if (!node) {
                node = createClashPieceNode(p);
                clashPieceNodes.set(p.id, node);
            }

            const expectedKey = `${p.color}_${p.type}`;
            if (node.pieceKey !== expectedKey) {
                node.pieceKey = expectedKey;
                node.glyph.innerHTML = getPieceSvgMarkup(p.type, p.color);
            }

            let ex = Math.max(0, Math.min(7, p.x + p.vx * dtSec));
            let ey = Math.max(0, Math.min(7, p.y + p.vy * dtSec));
            if (isReversed) {
                ex = 7 - ex;
                ey = 7 - ey;
            }
            node.root.style.transform = `translate3d(${ex * 100}%, ${ey * 100}%, 0)`;

            node.root.className = `clash-piece piece-${p.color} state-${p.state.toLowerCase()}` +
                (p.id === selectedClashPieceId ? ' is-selected' : '');

            if ((p.state === 'ACTIVATING' || p.state === 'COOLDOWN') && p.state_duration > 0) {
                const rem = Math.max(0, p.state_timer - dtSec);
                const frac = Math.max(0, Math.min(1, rem / p.state_duration));
                node.svg.style.display = 'block';
                node.fgCircle.style.strokeDashoffset = `${CLASH_RING_CIRCUMFERENCE * (1 - frac)}`;
                node.timerBadge.innerText = `${rem.toFixed(1)}s`;
                node.timerBadge.classList.remove('hidden');
            } else {
                node.svg.style.display = 'none';
                node.timerBadge.classList.add('hidden');
            }

            if (p.is_airborne) {
                const liftPx = p.jump_height * 18;
                const scale = 1 + p.jump_height * 0.25;
                node.glyph.style.transform = `translateY(${-liftPx}px) scale(${scale})`;
                node.shadow.style.opacity = `${0.25 + p.jump_height * 0.55}`;
                node.root.style.zIndex = '12';
            } else {
                node.glyph.style.transform = '';
                node.shadow.style.opacity = '0';
                node.root.style.zIndex = '4';
            }

            // Target reticle ONLY for player's own moving pieces (never opponent's).
            if (p.color === player_color && p.target && p.state === 'MOVING') {
                seenTargets.add(p.id);
                let targetEl = clashTargetNodes.get(p.id);
                if (!targetEl) {
                    targetEl = document.createElement('div');
                    targetEl.className = 'clash-piece';
                    const reticle = document.createElement('div');
                    reticle.className = 'clash-own-target';
                    targetEl.appendChild(reticle);
                    layer.appendChild(targetEl);
                    clashTargetNodes.set(p.id, targetEl);
                }
                const tx = isReversed ? 7 - p.target[1] : p.target[1];
                const ty = isReversed ? 7 - p.target[0] : p.target[0];
                targetEl.style.transform = `translate3d(${tx * 100}%, ${ty * 100}%, 0)`;
            }
        }

        for (const [pid, node] of clashPieceNodes.entries()) {
            if (!seenPieces.has(pid)) {
                node.root.remove();
                clashPieceNodes.delete(pid);
            }
        }
        for (const [pid, targetEl] of clashTargetNodes.entries()) {
            if (!seenTargets.has(pid)) {
                targetEl.remove();
                clashTargetNodes.delete(pid);
            }
        }
    }

    renderClashFx(frameDt);
    clashAnimFrameId = requestAnimationFrame(clashRenderLoop);
}

function renderClashFx(dt) {
    resizeClashCanvas();
    const canvas = document.getElementById('clash-fx-canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx || canvas.width === 0 || canvas.height === 0) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const isReversed = player_color === 'black';
    const sqW = canvas.width / 8;
    const sqH = canvas.height / 8;

    for (let i = clashShockwaves.length - 1; i >= 0; i--) {
        const sw = clashShockwaves[i];
        sw.life += dt;
        if (sw.life >= sw.maxLife) {
            clashShockwaves.splice(i, 1);
            continue;
        }
        const t = sw.life / sw.maxLife;
        const cx = (isReversed ? 8 - sw.bx : sw.bx) * sqW;
        const cy = (isReversed ? 8 - sw.by : sw.by) * sqH;
        const radius = sw.maxRadius * sqW * t;
        ctx.save();
        ctx.globalAlpha = 1 - t;
        ctx.strokeStyle = sw.color;
        ctx.lineWidth = 3 * (1 - t) + 1;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    }

    for (let i = clashParticles.length - 1; i >= 0; i--) {
        const pt = clashParticles[i];
        pt.life += dt;
        if (pt.life >= pt.maxLife) {
            clashParticles.splice(i, 1);
            continue;
        }
        pt.bx += pt.vx * dt;
        pt.by += pt.vy * dt;
        const alpha = 1 - pt.life / pt.maxLife;
        const px = (isReversed ? 8 - pt.bx : pt.bx) * sqW;
        const py = (isReversed ? 8 - pt.by : pt.by) * sqH;
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = pt.color;
        ctx.beginPath();
        ctx.arc(px, py, pt.size * (0.4 + 0.6 * alpha), 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }
}

function clearClashDropHover() {
    if (clashDragState && clashDragState.hoveredCell) {
        clashDragState.hoveredCell.classList.remove('clash-drop-hover');
        clashDragState.hoveredCell = null;
    }
}

function getBoardSquareFromPoint(clientX, clientY) {
    const el = document.elementFromPoint(clientX, clientY);
    if (!el) return null;
    const td = el.closest('#chessboard td[data-r]');
    if (!td) return null;
    return {
        td,
        row: parseInt(td.dataset.r, 10),
        col: parseInt(td.dataset.c, 10)
    };
}

function onClashDeckPointerDown(e) {
    if (!clashModeActive || !clashSnapshot || !clashSnapshot.started || !current_state || current_state.status !== 'playing') {
        return;
    }
    const card = e.currentTarget;
    const pieceType = card.dataset.piece;
    const cost = CLASH_SPAWN_COSTS[pieceType] || 99;
    if (getLiveClashEnergy() + 1e-6 < cost) {
        return;
    }
    e.preventDefault();
    clashDragState = {
        pieceType,
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        dragging: false,
        hoveredCell: null
    };
}

function onClashDeckPointerMove(e) {
    if (!clashDragState || e.pointerId !== clashDragState.pointerId) return;
    const dist = Math.hypot(e.clientX - clashDragState.startX, e.clientY - clashDragState.startY);
    const ghost = document.getElementById('clash-drag-ghost');

    if (!clashDragState.dragging && dist > 8) {
        clashDragState.dragging = true;
        selectedClashDeckPiece = clashDragState.pieceType;
        selectedClashPieceId = null;
        ghost.innerHTML = getPieceSvgMarkup(clashDragState.pieceType, player_color);
        ghost.classList.remove('hidden');
        refreshClashBoardHighlights();
    }

    if (clashDragState.dragging) {
        ghost.style.left = `${e.clientX}px`;
        ghost.style.top = `${e.clientY}px`;

        clearClashDropHover();
        const hit = getBoardSquareFromPoint(e.clientX, e.clientY);
        if (hit && isInOwnSpawnHalf(hit.row) && isClashSquareEmptyForSpawn(hit.row, hit.col)) {
            hit.td.classList.add('clash-drop-hover');
            clashDragState.hoveredCell = hit.td;
        }
    }
}

function onClashDeckPointerUp(e) {
    if (!clashDragState || e.pointerId !== clashDragState.pointerId) return;
    const state = clashDragState;
    clashDragState = null;

    const ghost = document.getElementById('clash-drag-ghost');
    ghost.classList.add('hidden');
    if (state.hoveredCell) state.hoveredCell.classList.remove('clash-drop-hover');

    if (state.dragging) {
        const hit = getBoardSquareFromPoint(e.clientX, e.clientY);
        if (hit && isInOwnSpawnHalf(hit.row) && isClashSquareEmptyForSpawn(hit.row, hit.col)) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'clash_spawn',
                    piece: state.pieceType,
                    row: hit.row,
                    col: hit.col
                }));
            }
        }
        selectedClashDeckPiece = null;
    } else {
        // Simple click/tap: toggle deck card selection for click-to-spawn.
        selectedClashPieceId = null;
        selectedClashDeckPiece = (selectedClashDeckPiece === state.pieceType) ? null : state.pieceType;
        const statusEl = document.getElementById('status-message');
        if (selectedClashDeckPiece) {
            statusEl.innerText = "Cliquez une case vide dans votre moitié de terrain";
        } else if (clashSnapshot && clashSnapshot.started) {
            statusEl.innerText = "Temps réel — Invoquez et déplacez librement !";
        }
    }
    refreshClashBoardHighlights();
}

function onClashDeckPointerCancel(e) {
    if (!clashDragState || e.pointerId !== clashDragState.pointerId) return;
    document.getElementById('clash-drag-ghost').classList.add('hidden');
    clearClashDropHover();
    clashDragState = null;
    selectedClashDeckPiece = null;
    refreshClashBoardHighlights();
}

function onClashSquareClick(e) {
    if (!clashModeActive || !clashSnapshot || !clashSnapshot.started || !current_state || current_state.status !== 'playing') {
        return;
    }

    const r = parseInt(e.currentTarget.dataset.r, 10);
    const c = parseInt(e.currentTarget.dataset.c, 10);

    // 1. Click-to-spawn when a deck card is selected.
    if (selectedClashDeckPiece) {
        const cost = CLASH_SPAWN_COSTS[selectedClashDeckPiece] || 99;
        if (isInOwnSpawnHalf(r) && isClashSquareEmptyForSpawn(r, c) && getLiveClashEnergy() + 1e-6 >= cost) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'clash_spawn',
                    piece: selectedClashDeckPiece,
                    row: r,
                    col: c
                }));
            }
            selectedClashDeckPiece = null;
            refreshClashBoardHighlights();
            return;
        }
        selectedClashDeckPiece = null;
    }

    // 2. Execute move if a board piece is selected and destination is legal.
    if (selectedClashPieceId) {
        const selPiece = clashSnapshot.pieces.find(p => p.id === selectedClashPieceId);
        if (selPiece && selPiece.state === 'ACTIVE') {
            const targets = getClientClashLegalTargets(selPiece);
            const match = targets.find(t => t.row === r && t.col === c);
            if (match) {
                const moveCost = CLASH_MOVE_COSTS[selPiece.type] || 1;
                if (getLiveClashEnergy() + 1e-6 >= moveCost && ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        type: 'clash_move',
                        piece_id: selPiece.id,
                        to: [r, c]
                    }));
                }
                selectedClashPieceId = null;
                refreshClashBoardHighlights();
                return;
            }
        }
    }

    // 3. Select/deselect own ACTIVE stationary piece on clicked square.
    const ownActive = clashSnapshot.pieces.find(
        p => p.color === player_color && p.state === 'ACTIVE' && p.row === r && p.col === c
    );
    if (ownActive) {
        selectedClashPieceId = (selectedClashPieceId === ownActive.id) ? null : ownActive.id;
    } else {
        selectedClashPieceId = null;
    }
    refreshClashBoardHighlights();
}
