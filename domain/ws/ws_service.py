"""
============================================================================
[백엔드 실시간 웹소켓 커넥션 매니저 (domain/ws/ws_service.py)]
============================================================================

💡 이 파일의 역할:
전체 실시간 웹소켓(/ws) 연결을 관리하며, 단순 전체 브로드캐스트뿐만 아니라
소켓별 소유자(user_id) 및 기기 카테고리(DESKTOP / MOBILE) 메타데이터를 추적하여
특정 사용자·특정 기기(예: 데스크톱 ↔ 스마트폰 지문 공조)로만 정확히 타겟 라우팅합니다.

🌟 4대 정석 아키텍처 핵심:
1. [소켓별 소유자·기기 메타데이터 추적 (connection_meta)]:
   - 각 WebSocket 연결마다 `{ user_id, username, device_category }`를 매핑하여 관리합니다.
2. [사용자별/기기별 정밀 타겟 라우팅 (send_to_user)]:
   - 타 직원이나 발신 데스크톱 자신에게 불필요한 신호가 새어나가지 않도록,
     동일 `user_id`의 `MOBILE` 또는 `DESKTOP` 기기로만 정확히 메시지를 전달합니다.
3. [사용자별 원격 공조 대기열 격리 (pending_coop_requests)]:
   - 전역 단일 변수가 아닌 `dict[int, dict]` 구조로 사원(`user_id`)별 원격 지문 요청을 격리 보관합니다.
4. [Graceful Shutdown (close_all)]:
   - Uvicorn 리로드 또는 서버 종료 시 열려 있는 모든 웹소켓을 즉시 정상 종료(1001)하여
     구버전 워커 프로세스가 좀비처럼 남는 현상을 원천 차단합니다.
"""

from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # 각 웹소켓 인스턴스별 메타데이터: { ws: {"user_id": int, "username": str, "device_category": "DESKTOP"|"MOBILE"} }
        self.connection_meta: dict[WebSocket, dict] = {}
        # 사용자(user_id)별 대기 중인 원격 지문 공조 요청: { user_id: dict }
        self.pending_coop_requests: dict[int, dict] = {}

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int | None = None,
        username: str | None = None,
        device_category: str = "DESKTOP",
    ):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_meta[websocket] = {
            "user_id": user_id,
            "username": username or "user",
            "device_category": device_category,
        }

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.connection_meta.pop(websocket, None)

    def get_meta(self, websocket: WebSocket) -> dict:
        return self.connection_meta.get(websocket, {})

    async def send_to_user(
        self,
        user_id: int,
        message: dict,
        target_device: str | None = None,
        exclude_ws: WebSocket | None = None,
    ) -> int:
        """
        특정 사용자(user_id)의 연결된 소켓들로만 메시지를 타겟 전송합니다.
        - target_device: "MOBILE" 또는 "DESKTOP" 지정 시 해당 기기 카테고리로만 전송 (None이면 해당 유저의 모든 기기)
        - exclude_ws: 발신자 소켓 자신을 제외할 때 지정
        """
        if not self.active_connections:
            return 0

        data_str = json.dumps(message, ensure_ascii=False)
        target_connections: list[WebSocket] = []

        for ws in list(self.active_connections):
            if ws is exclude_ws:
                continue
            meta = self.connection_meta.get(ws)
            if not meta or meta.get("user_id") != user_id:
                continue
            if target_device and meta.get("device_category") != target_device:
                continue
            target_connections.append(ws)

        if not target_connections:
            return 0

        tasks = [ws.send_text(data_str) for ws in target_connections]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        sent_count = 0
        for ws, result in zip(target_connections, results):
            if isinstance(result, (WebSocketDisconnect, Exception)):
                self.disconnect(ws)
            else:
                sent_count += 1
        return sent_count

    async def broadcast(self, message: dict, exclude_ws: WebSocket | None = None):
        """프로젝트 어디서든 이 함수를 호출하여 전체 클라이언트에게 메시지 브로드캐스트 (특정 발신 소켓 제외 가능)"""
        if not self.active_connections:
            return
        data_str = json.dumps(message, ensure_ascii=False)

        target_connections = [
            ws for ws in list(self.active_connections) if ws is not exclude_ws
        ]
        if not target_connections:
            return

        # 병렬 전송
        tasks = [ws.send_text(data_str) for ws in target_connections]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 연결 끊긴 클라이언트 정리
        for ws, result in zip(target_connections, results):
            if isinstance(result, (WebSocketDisconnect, Exception)):
                self.disconnect(ws)

    def broadcast_sync(self, message: dict):
        """동기 컨텍스트(워커, 백그라운드 스레드 등)에서 안전하게 브로드캐스트를 비동기 스케줄링"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.broadcast(message))
            else:
                loop.run_until_complete(self.broadcast(message))
        except Exception:
            pass

    async def ping_all(self):
        """연결 유지 확인 (Heartbeat)"""
        if not self.active_connections:
            return
        data_str = json.dumps({"type": "ping"})
        target_connections = list(self.active_connections)
        tasks = [ws.send_text(data_str) for ws in target_connections]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for ws, result in zip(target_connections, results):
            if isinstance(result, (WebSocketDisconnect, Exception)):
                self.disconnect(ws)

    async def close_all(self):
        """서버 종료/리로드 시 열려 있는 모든 웹소켓을 안전하게 닫아 워커 블로킹을 방지합니다."""
        target_connections = list(self.active_connections)
        self.active_connections.clear()
        self.connection_meta.clear()
        if not target_connections:
            return
        tasks = [ws.close(code=1001) for ws in target_connections]
        await asyncio.gather(*tasks, return_exceptions=True)


# 전역 매니저 인스턴스
manager = ConnectionManager()


async def ping_loop():
    """주기적으로 모든 클라이언트에게 ping을 보내 연결을 유지합니다."""
    while True:
        await manager.ping_all()
        await asyncio.sleep(60)
