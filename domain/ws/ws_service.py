from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """프로젝트 어디서든 이 함수를 호출하여 전체 클라이언트에게 메시지 브로드캐스트"""
        if not self.active_connections:
            return
        data_str = json.dumps(message, ensure_ascii=False)
        
        # 병렬 전송
        tasks = [ws.send_text(data_str) for ws in self.active_connections]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 연결 끊긴 클라이언트 정리
        for i, result in enumerate(results):
            if isinstance(result, (WebSocketDisconnect, Exception)):
                if i < len(self.active_connections):
                    self.disconnect(self.active_connections[i])

    async def ping_all(self):
        """연결 유지 확인 (Heartbeat)"""
        if not self.active_connections:
            return
        data_str = json.dumps({"type": "ping"})
        tasks = [ws.send_text(data_str) for ws in self.active_connections]
        await asyncio.gather(*tasks, return_exceptions=True)

# 전역 매니저 인스턴스
manager = ConnectionManager()

async def ping_loop():
    """주기적으로 모든 클라이언트에게 ping을 보내 연결을 유지합니다."""
    while True:
        await manager.ping_all()
        await asyncio.sleep(60)
