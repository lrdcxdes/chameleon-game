# main.py
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from game_logic import Game

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
rooms = {}


@app.get("/", response_class=HTMLResponse)
async def get():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.websocket("/ws/{room_code}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, player_name: str):
    room_code = room_code.upper()
    player_name = player_name.strip()

    if room_code not in rooms:
        rooms[room_code] = Game(room_code)
    game = rooms[room_code]

    if player_name in game.players:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Игрок с таким именем уже в комнате."})
        await websocket.close()
        return

    await websocket.accept()
    await game.add_player(player_name, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "player_ready":
                is_ready = data.get("is_ready", False)
                await game.handle_ready(player_name, is_ready)

            elif action == "submit_association":
                word = data.get("word")
                await game.handle_association(player_name, word)

            elif action == "submit_vote":
                voted_for = data.get("voted_for")
                await game.handle_vote(player_name, voted_for)

    except WebSocketDisconnect:
        await game.remove_player(player_name)
        if not game.players:
            if room_code in rooms:
                del rooms[room_code]
                print(f"Room {room_code} closed.")


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)