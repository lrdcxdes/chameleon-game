// static/script.js
// --- DOM Элементы ---
const lobby = document.getElementById('lobby');
const gameArea = document.getElementById('game-area');
const playerNameInput = document.getElementById('player-name-input');
const roomCodeInput = document.getElementById('room-code-input');
const joinRoomBtn = document.getElementById('join-room-btn');
const createRoomBtn = document.getElementById('create-room-btn');
const errorMessage = document.getElementById('error-message');

const roomCodeDisplay = document.getElementById('room-code-display');
const playerNameDisplay = document.getElementById('player-name-display');
const roundDisplay = document.getElementById('round-display');
const timerDisplay = document.getElementById('timer-display');
const playerList = document.getElementById('player-list');
const readyBtn = document.getElementById('ready-btn');
const statusText = document.getElementById('status-text');
const wordDisplayContainer = document.getElementById('word-display-container');
const secretWordDisplay = document.getElementById('secret-word-display');
const associationListContainer = document.getElementById('association-list-container');
const associationList = document.getElementById('association-list');
const actionContainer = document.getElementById('action-container');
const actionInput = document.getElementById('action-input');
const actionBtn = document.getElementById('action-btn');
const voteContainer = document.getElementById('vote-container');
const voteButtons = document.getElementById('vote-buttons');
const revealOverlay = document.getElementById('reveal-overlay');
const revealContent = document.getElementById('reveal-content');

// --- Состояние клиента ---
let socket;
let playerName;
let roomCode;
let isReady = false;
let hasSubmittedAssociation = false;

// --- Функции ---
function generateRoomCode() {
    return Math.random().toString(36).substring(2, 6).toUpperCase();
}

function connectWebSocket() {
    playerName = playerNameInput.value.trim();
    roomCode = roomCodeInput.value.trim().toUpperCase();
    if (!playerName || !roomCode) {
        errorMessage.textContent = "Имя и код комнаты не могут быть пустыми.";
        return;
    }
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${roomCode}/${playerName}`;
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        lobby.classList.add('hidden');
        gameArea.classList.remove('hidden');
        roomCodeDisplay.textContent = roomCode;
        playerNameDisplay.textContent = playerName;
        readyBtn.classList.remove('hidden');
    };
    socket.onmessage = (event) => handleServerMessage(JSON.parse(event.data));
    socket.onclose = () => {
        alert("Соединение с сервером потеряно.");
        window.location.reload();
    };
    socket.onerror = () => errorMessage.textContent = "Ошибка подключения.";
}

function sendMessage(data) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(data));
    }
}

function handleServerMessage(data) {
    console.log("Received data:", data);
    switch(data.type) {
        case 'error':
            socket.close();
            alert(data.message);
            window.location.reload();
            break;
        case 'update_players':
            updatePlayerList(data.players);
            break;
        case 'timer_update':
            timerDisplay.textContent = data.time > 0 ? data.time : '';
            break;
        case 'game_start':
            resetUIForNewRound();
            roundDisplay.textContent = `Раунд ${data.round}`;
            secretWordDisplay.textContent = data.word;
            wordDisplayContainer.classList.remove('hidden');
            break;
        case 'state_change':
            handleStateChange(data);
            break;
        case 'association_update':
            updateAssociationList(data.associations);
            break;
        case 'vote_update':
            const voterLi = Array.from(playerList.children).find(li => li.textContent.startsWith(data.voter));
            if (voterLi) voterLi.classList.add('voted');
            break;
        case 'reveal':
            revealOverlay.classList.remove('hidden');
            let winnerText = data.winner === 'peaceful' ? 'МИРНЫЕ ПОБЕДИЛИ!' : 'ХАМЕЛЕОН ПОБЕДИЛ!';
            if(data.voted_out === "НИЧЬЯ") winnerText = "НИЧЬЯ В ГОЛОСОВАНИИ!";
            let resultHTML = `<h2>${winnerText}</h2>
                <p>Изгнан: ${data.voted_out}</p>
                <p>Хамелеон: ${data.chameleon}</p>
                <p>Секретное слово: ${data.secret_word}</p>`;
            revealContent.innerHTML = resultHTML;
            break;
        case 'reset':
            resetToLobby(data.message);
            break;
    }
}

function handleStateChange(data) {
    updateAssociationList(data.associations);
    associationListContainer.classList.remove('hidden');
    hasSubmittedAssociation = false; // Сброс для нового круга ассоциаций
    actionInput.disabled = false;

    if (data.state.startsWith('associating')) {
        const phase = data.state.split('_')[1];
        statusText.textContent = `Придумайте ассоциацию (${phase}/2)`;
        actionContainer.classList.remove('hidden');
    } else if (data.state === 'voting') {
        statusText.textContent = "Время голосовать!";
        actionContainer.classList.add('hidden');
        setupVoteButtons();
    }
}

function updatePlayerList(playersData) {
    playerList.innerHTML = '';
    Object.entries(playersData).forEach(([name, data]) => {
        const li = document.createElement('li');
        li.textContent = name;
        if (data.is_ready) li.classList.add('ready');
        playerList.appendChild(li);
    });
}

function updateAssociationList(associations) {
    associationList.innerHTML = '';
    for(const [player, word] of Object.entries(associations)) {
        const li = document.createElement('li');
        li.textContent = `${player}: ${word}`;
        associationList.appendChild(li);
        if (player === playerName) { // Если мы уже ответили
            hasSubmittedAssociation = true;
            actionInput.disabled = true;
        }
    }
}

function setupVoteButtons() {
    voteContainer.classList.remove('hidden');
    voteButtons.innerHTML = '';
    const players = Array.from(playerList.children).map(li => li.textContent.replace(/\[.\]/g, '').trim());
    players.forEach(p => {
        if (p !== playerName) {
            const btn = document.createElement('button');
            btn.textContent = p;
            btn.onclick = () => {
                sendMessage({ action: 'submit_vote', voted_for: p });
                voteContainer.classList.add('hidden');
                statusText.textContent = "Вы проголосовали. Ожидаем других...";
            };
            voteButtons.appendChild(btn);
        }
    });
}

function resetUIForNewRound() {
    readyBtn.classList.add('hidden');
    isReady = false;
    readyBtn.classList.remove('toggled');
    readyBtn.textContent = 'ГОТОВ';
    statusText.textContent = '';
    associationListContainer.classList.add('hidden');
    actionContainer.classList.add('hidden');
    voteContainer.classList.add('hidden');
    revealOverlay.classList.add('hidden');
}

function resetToLobby(message) {
    if(message) alert(message);
    resetUIForNewRound();
    readyBtn.classList.remove('hidden');
    roundDisplay.textContent = 'Лобби';
    statusText.textContent = 'Ожидание игроков...';
    wordDisplayContainer.classList.add('hidden');
}

// --- Привязка событий ---
createRoomBtn.addEventListener('click', () => {
    roomCodeInput.value = generateRoomCode();
    connectWebSocket();
});

joinRoomBtn.addEventListener('click', connectWebSocket);

readyBtn.addEventListener('click', () => {
    isReady = !isReady;
    readyBtn.classList.toggle('toggled');
    readyBtn.textContent = isReady ? 'НЕ ГОТОВ' : 'ГОТОВ';
    sendMessage({ action: 'player_ready', is_ready: isReady });
});

actionBtn.addEventListener('click', () => {
    const word = actionInput.value.trim();
    if(word && !hasSubmittedAssociation) {
        sendMessage({ action: 'submit_association', word: word });
        actionInput.value = '';
    }
});
actionInput.addEventListener('keyup', (e) => e.key === 'Enter' && actionBtn.click());