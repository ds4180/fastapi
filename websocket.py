# main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.editor: str = None  # 현재 편집자 (IP 주소 기준)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if self.editor == websocket.client.host:
            self.editor = None

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            # 편집 시작 요청
            if action == "start_edit":
                if manager.editor is None:
                    manager.editor = websocket.client.host
                    await manager.broadcast({"type": "edit_status", "editor": "someone"})
                else:
                    # 이미 편집중이면 거부
                    await websocket.send_json({"type": "edit_status", "editor": manager.editor})

            # 편집 종료
            elif action == "stop_edit":
                if manager.editor == websocket.client.host:
                    manager.editor = None
                    await manager.broadcast({"type": "edit_status", "editor": None})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast({"type": "edit_status", "editor": manager.editor})
