# game_logic.py
import random
import asyncio

# --- Константы таймеров (в секундах) ---
PRE_GAME_COUNTDOWN = 5
ASSOCIATION_TIME = 30
VOTING_TIME = 25
REVEAL_TIME = 15


class Game:
    def __init__(self, room_code: str):
        self.room_code = room_code
        self.players = {}  # {player_name: websocket}
        self.ready_players = set()
        self.state = "waiting"
        self.word_list = self._load_words()
        self.game_timer = None
        # --- Состояние раунда ---
        self.round_number = 0
        self.secret_word = ""
        self.chameleon = ""
        self.associations = {}
        self.votes = {}

    def _load_words(self):
        with open("words.txt", "r", encoding="utf-8") as f:
            return [line.strip().upper() for line in f.readlines()]

    async def _cancel_timer(self):
        """Безопасно отменяет текущий таймер."""
        if self.game_timer:
            self.game_timer.cancel()
            self.game_timer = None

    async def broadcast(self, message: dict):
        websockets = self.players.values()
        for websocket in websockets:
            await websocket.send_json(message)

    async def add_player(self, player_name: str, websocket):
        self.players[player_name] = websocket
        await self.broadcast_player_list()

    async def remove_player(self, player_name: str):
        if player_name in self.players:
            del self.players[player_name]
        if player_name in self.ready_players:
            self.ready_players.remove(player_name)

        if self.state != "waiting":
            await self.reset_game("Игрок вышел. Игра сброшена.")
        else:
            await self.broadcast_player_list()
            # Проверить, не стали ли все готовы после выхода игрока
            await self.check_all_ready()

    async def broadcast_player_list(self):
        player_data = {
            name: {"is_ready": name in self.ready_players}
            for name in self.players.keys()
        }
        await self.broadcast({"type": "update_players", "players": player_data})

    async def handle_ready(self, player_name: str, is_ready: bool):
        if self.state != "waiting": return

        if is_ready:
            self.ready_players.add(player_name)
        else:
            self.ready_players.discard(player_name)

        await self.broadcast_player_list()
        await self.check_all_ready()

    async def check_all_ready(self):
        num_players = len(self.players)
        if num_players >= 3 and num_players == len(self.ready_players):
            await self._cancel_timer()
            self.game_timer = asyncio.create_task(self.run_countdown(PRE_GAME_COUNTDOWN, self.start_game))
        else:
            # Если кто-то нажал "не готов", отменяем предстартовый отсчет
            await self._cancel_timer()
            await self.broadcast({"type": "timer_update", "time": 0})

    async def run_countdown(self, duration: int, on_finish_callback):
        """Запускает обратный отсчет, видимый для всех, и вызывает колбэк."""
        for i in range(duration, 0, -1):
            await self.broadcast({"type": "timer_update", "time": i})
            await asyncio.sleep(1)
        await self.broadcast({"type": "timer_update", "time": 0})
        await on_finish_callback()

    async def start_game(self):
        self.state = "associating_1"
        self.round_number += 1
        self.secret_word = random.choice(self.word_list)
        player_names = list(self.players.keys())
        self.chameleon = random.choice(player_names)
        self.associations = {}
        self.votes = {}

        for name, ws in self.players.items():
            role_info = {"type": "game_start", "round": self.round_number}
            role_info["role"] = "chameleon" if name == self.chameleon else "peaceful"
            role_info["word"] = "???" if name == self.chameleon else self.secret_word
            await ws.send_json(role_info)

        await self.start_association_phase(1)

    async def start_association_phase(self, phase_num: int):
        self.state = f"associating_{phase_num}"
        self.associations = {}  # Очищаем для нового круга
        await self.broadcast({
            "type": "state_change", "state": self.state,
            "round": self.round_number, "associations": self.associations
        })
        # Запускаем таймер. Если он закончится, перейдем к следующей фазе принудительно
        await self._cancel_timer()
        self.game_timer = asyncio.create_task(
            self.run_countdown(ASSOCIATION_TIME, self.force_end_association_phase)
        )

    async def handle_association(self, player_name: str, word: str):
        if self.state not in ["associating_1", "associating_2"] or player_name in self.associations:
            return

        self.associations[player_name] = word
        # Отправляем всем обновленный список, чтобы было видно, кто ответил
        await self.broadcast({"type": "association_update", "associations": self.associations})

        if len(self.associations) == len(self.players):
            await self._cancel_timer()
            await self.finish_association_phase()

    async def force_end_association_phase(self):
        # Для всех, кто не ответил, ставим "..."
        for player in self.players:
            if player not in self.associations:
                self.associations[player] = "..."
        await self.finish_association_phase()

    async def finish_association_phase(self):
        if self.state == "associating_1":
            await self.start_association_phase(2)
        elif self.state == "associating_2":
            await self.start_voting_phase()

    async def start_voting_phase(self):
        self.state = "voting"
        self.votes = {}
        await self.broadcast({
            "type": "state_change", "state": self.state,
            "round": self.round_number, "associations": self.associations
        })
        await self._cancel_timer()
        self.game_timer = asyncio.create_task(
            self.run_countdown(VOTING_TIME, self.tally_votes)
        )

    async def handle_vote(self, voter_name: str, voted_for: str):
        if self.state != "voting" or voter_name in self.votes: return
        self.votes[voter_name] = voted_for
        await self.broadcast({"type": "vote_update", "voter": voter_name})

        if len(self.votes) == len(self.players):
            await self._cancel_timer()
            await self.tally_votes()

    async def tally_votes(self):
        self.state = "reveal"
        vote_counts = {}
        for vote in self.votes.values():
            vote_counts[vote] = vote_counts.get(vote, 0) + 1

        voted_out = "НИЧЬЯ"
        winner = "chameleon"  # Хамелеон побеждает при ничьей
        if vote_counts:
            max_votes = max(vote_counts.values())
            voted_out_players = [p for p, v in vote_counts.items() if v == max_votes]
            if len(voted_out_players) == 1:
                voted_out = voted_out_players[0]
                winner = "peaceful" if voted_out == self.chameleon else "chameleon"

        await self.broadcast({
            "type": "reveal", "voted_out": voted_out, "chameleon": self.chameleon,
            "secret_word": self.secret_word, "winner": winner, "votes": self.votes
        })
        await self._cancel_timer()
        self.game_timer = asyncio.create_task(
            self.run_countdown(REVEAL_TIME, self.reset_game)
        )

    async def reset_game(self, message_text: str = None):
        self.state = "waiting"
        self.ready_players = set()
        await self.broadcast({"type": "reset", "message": message_text or "Готовьтесь к новому раунду!"})
        await self.broadcast_player_list()