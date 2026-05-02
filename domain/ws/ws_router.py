from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from domain.ws.ws_service import manager
import json

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 클라이언트로부터 메시지 수신 (pong 등)
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
                if data.get("type") == "pong":
                    continue
            except:
                continue
    except WebSocketDisconnect:
        manager.disconnect(websocket)
