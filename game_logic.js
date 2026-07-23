let game_room = localStorage.getItem('chess_room_id') || null;
let player_color = localStorage.getItem('chess_player_color') || null;

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.has('join')) {
    game_room = urlParams.get('join');
    player_color = 'black'; 
    localStorage.setItem('chess_room_id', game_room);
    localStorage.setItem('chess_player_color', player_color);
}

const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const host = window.location.host || "localhost:8000";

const WS_URL = `${wsProtocol}//${host}/ws`;
const API_URL = `${protocol}//${host}`;

let ws;
let current_state = null;
let selected_pos = null; 

const PIECES = {
    'r': '♜', 'n': '♞', 'b': '♝', 'q': '♛', 'k': '♚', 'p': '♟',
    'R': '♖', 'N': '♘', 'B': '♗', 'Q': '♕', 'K': '♔', 'P': '♙'
};

const VARIANT_NAMES = {
    'classic': 'Classique', 'chess960': 'Chess 960', 'clubhouse': 'Club House',
    'fog': 'Brouillard de Guerre', 'antichess': 'Qui perd gagne',
    'hidden_queen': 'Dame Cachée', 'bataille': 'Bataille Chess'
};

document.addEventListener('DOMContentLoaded', () => {
    initUI();
    if (game_room && player_color) joinGame(game_room, player_color);
});

function initUI() {
    document.getElementById('create-game-btn').addEventListener('click', async () => {
        const variant = document.getElementById('variant-select').value;
        try {
            const response = await fetch(`${API_URL}/create_room?variant=${variant}`, { method: 'POST' });
            const data = await response.json();
            player_color = 'white';
            localStorage.setItem('chess_player_color', player_color);
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
        if(current_state && current_state.bataille_bench.length === 0) {
            ws.send(JSON.stringify({type: 'bataille_ready'}));
        } else {
            alert("Placez toutes vos pièces d'abord !");
        }
    });

    document.querySelectorAll('.promo-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const piece = e.currentTarget.dataset.piece;
            ws.send(JSON.stringify({type: 'promote', piece: piece}));
        });
    });
}

function abandonGame() {
    localStorage.removeItem('chess_room_id');
    localStorage.removeItem('chess_player_color');
    window.location.href = window.location.pathname;
}

function joinGame(room_id, color) {
    game_room = room_id;
    player_color = color;
    localStorage.setItem('chess_room_id', game_room);
    
    document.getElementById('header').classList.add('hidden');
    const shareUrl = new URL(window.location.href);
    shareUrl.searchParams.set('join', room_id);
    document.getElementById('lobby-share-link').value = shareUrl.toString();
    document.getElementById('room-id-display').innerText = room_id;
    document.getElementById('lobby-area').classList.remove('hidden');

    ws = new WebSocket(`${WS_URL}/${game_room}/${player_color}`);
    ws.onmessage = (event) => {
        current_state = JSON.parse(event.data);
        if (current_state.players_count === 2) {
            document.getElementById('lobby-area').classList.add('hidden');
            document.getElementById('game-area').classList.remove('hidden');
        }
        document.getElementById('variant-title').innerText = "Mode : " + VARIANT_NAMES[current_state.variant];
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
        go.innerText = current_state.winner === 'draw' ? "Match Nul / Égalité parfaite !" : `Le joueur ${current_state.winner} gagne !`;
        document.getElementById('status-message').innerText = "Partie terminée";
        document.getElementById('promotion-modal').classList.add('hidden');
        return;
    }
    
    if (current_state.status === 'awaiting_promotion') {
        if (current_state.turn === player_color) {
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
        else if (!current_state.bataille_ready[current_state.turn === 'white' ? 'black' : 'white']) msg = "Adversaire place ses pièces...";
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

    for (let r = 0; r < 8; r++) {
        const rowData = isReversed ? 7 - r : r;
        const tr = document.createElement('tr');
        for (let c = 0; c < 8; c++) {
            const colData = isReversed ? 7 - c : c;
            const piece = current_state.board[rowData][colData];
            const td = document.createElement('td');
            td.className = ((rowData + colData) % 2 === 1) ? 'dark-square' : 'light-square';
            
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
                span.innerText = PIECES[piece] || piece;
                span.style.color = piece === piece.toUpperCase() ? '#fff' : '#000';
                if(piece === piece.toUpperCase()) span.style.textShadow = '0px 0px 2px #000';
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
            div.innerText = PIECES[p] || p;
            div.style.color = p === p.toUpperCase() ? '#fff' : '#000';
            if (p === p.toUpperCase()) div.style.textShadow = '0px 0px 2px #000';
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
            div.innerText = PIECES[p] || p;
            div.style.color = p === p.toUpperCase() ? '#fff' : '#000';
            if (p === p.toUpperCase()) div.style.textShadow = '0px 0px 2px #000';
            
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
            div.innerText = PIECES[p] || p;
            div.style.color = p === p.toUpperCase() ? '#fff' : '#000';
            if (p === p.toUpperCase()) div.style.textShadow = '0px 0px 2px #000';
            oppPocket.appendChild(div);
        });
    }
}

function onSquareClick(e) {
    const r = parseInt(e.currentTarget.dataset.r);
    const c = parseInt(e.currentTarget.dataset.c);
    const piece = current_state.board[r][c];

    if (current_state.variant === 'bataille' && !current_state.bataille_ready[player_color]) {
        const allowedRanks = player_color === 'white' ? [4, 5, 6, 7] : [0, 1, 2, 3];
        if (typeof selected_pos === 'string' && selected_pos.startsWith('bench_') && allowedRanks.includes(r)) {
            const idx = parseInt(selected_pos.split('_')[1]);
            if (piece) return;
            const p = current_state.bataille_bench[idx];
            current_state.board[r][c] = p;
            current_state.bataille_bench.splice(idx, 1);
            selected_pos = null;
            ws.send(JSON.stringify({ type: 'bataille_place', board: current_state.board, bench: current_state.bataille_bench }));
            renderBoard();
        } else if (piece && allowedRanks.includes(r) && ((player_color === 'white' && piece === piece.toUpperCase()) || (player_color === 'black' && piece === piece.toLowerCase()))) {
             current_state.bataille_bench.push(piece);
             current_state.board[r][c] = '';
             ws.send(JSON.stringify({ type: 'bataille_place', board: current_state.board, bench: current_state.bataille_bench }));
             renderBoard();
        }
        return;
    }

    if (current_state.variant === 'hidden_queen' && !current_state.hq_chosen) {
        if (piece && piece.toLowerCase() === 'p' && ((player_color === 'white' && piece === piece.toUpperCase()) || (player_color === 'black' && piece === piece.toLowerCase()))) {
            if (confirm("Sélectionner ce pion comme Dame Cachée ?")) {
                ws.send(JSON.stringify({type: 'hidden_queen_setup', pos: [r, c]}));
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
                if (m.to[0] === r && m.to[1] === c) { moveFound = m; break; }
            }
        }

        if (moveFound) {
            ws.send(JSON.stringify({type: 'move', move: moveFound}));
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
