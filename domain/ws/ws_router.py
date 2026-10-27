from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from domain.ws.ws_service import manager
from database import SessionLocal
from core.session import validate_session
import json

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    [실시간 웹소켓 엔드포인트 (/ws)]
    
    💡 핵심 보안 및 커넥션 관리 규칙:
    1. 브라우저가 전송한 쿠키(session_id)를 추출하여 로그인된 유효 세션인지 먼저 검증합니다.
    2. 웹소켓은 장시간 연결이 유지되므로 Depends(get_db)를 사용하지 않고,
       핸드셰이크 시점에만 `with SessionLocal() as db:`로 짧게 검증한 뒤 DB 커넥션을 즉시 반납합니다.
       (DB 커넥션 풀 고갈 원천 차단!)
    3. 비로그인 또는 만료된 세션인 경우 1008(Policy Violation) 코드로 연결을 즉시 거부합니다.
    """
    session_id = websocket.cookies.get("session_id")
    if not session_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    with SessionLocal() as db:
        user = validate_session(db, session_id)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(websocket)
    try:
        while True:
            # 클라이언트로부터 메시지 수신 (pong 등)
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
                if data.get("type") == "pong":
                    continue
            except Exception:
                continue
    except WebSocketDisconnect:
        manager.disconnect(websocket)
