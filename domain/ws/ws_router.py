"""
============================================================================
[백엔드 실시간 웹소켓 라우터 (domain/ws/ws_router.py)]
============================================================================

💡 이 파일의 역할:
클라이언트와 `/ws` 단일 웹소켓 채널을 수립하고, 핸드셰이크 시점에 세션(`session_id`)과
접속 기기 유형(`DESKTOP` / `MOBILE`)을 판별하여 `ConnectionManager`에 등록합니다.

🌟 데스크톱 ↔ 스마트폰 원격 지문 공조 정석 라우팅:
1. 무인증 임시 HTTP 엔드포인트를 일절 사용하지 않고, 인증된 `/ws` 단일 소켓 프로토콜로만 중계합니다.
2. `BIOMETRIC_COOP_REQUEST` 수신 시:
   - 요청자의 `user_id` 전용 대기열(`manager.pending_coop_requests[user_id]`)에 60초 유효 요청으로 보관합니다.
   - `manager.send_to_user(user_id, data, target_device="MOBILE", exclude_ws=websocket)`를 통해
     **요청자 본인의 모바일 기기로만** 타겟 전송합니다 (발신 데스크톱 자신 및 타 사원 완전 배제).
   - 모바일 화면이 꺼져 있거나 백그라운드일 때를 대비해 `send_push_to_user(user_id, ...)`로
     **본인 기기에만** Web Push 알림을 동시 발송합니다.
3. 모바일 기기가 뒤늦게 `/ws`에 연결되거나 `BIOMETRIC_COOP_SYNC` 신호를 보낼 때:
   - 해당 `user_id` 앞으로 60초 이내의 대기 중인 요청이 있고 접속 기기가 `MOBILE`이면 즉시 전달합니다.
4. `BIOMETRIC_COOP_RESULT` / `BIOMETRIC_COOP_CANCEL` 수신 시:
   - 해당 `user_id`의 대기열을 즉시 비우고, 요청자 본인의 다른 기기(데스크톱 등)로만 결과를 전달합니다.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from domain.ws.ws_service import manager
from database import SessionLocal
from core.session import validate_session, detect_device_category
import asyncio
import json
import time

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
    4. User-Agent를 기반으로 기기 카테고리(DESKTOP / MOBILE)를 식별하여 타겟 라우팅에 활용합니다.
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
        user_id = user.id
        username = getattr(user, "username", None) or getattr(user, "email", "user")

    user_agent = websocket.headers.get("user-agent", "")
    device_category = detect_device_category(user_agent)

    await manager.connect(
        websocket,
        user_id=user_id,
        username=username,
        device_category=device_category,
    )

    # 📱 모바일 기기가 슬립 복귀 등으로 뒤늦게 연결된 경우, 본인(user_id)의 60초 이내 대기 요청이 있으면 즉시 전달
    if device_category == "MOBILE":
        pending = manager.pending_coop_requests.get(user_id)
        if pending and (time.time() - pending.get("_ts", 0) < 60):
            try:
                await websocket.send_text(json.dumps(pending, ensure_ascii=False))
            except Exception:
                pass

    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
                msg_type = data.get("type")

                if msg_type == "pong":
                    continue

                if msg_type == "BIOMETRIC_COOP_SYNC":
                    # 📱 모바일 화면 진입/복귀 시 대기 중인 본인 요청 동기화 (모바일 기기에서만 수신)
                    if device_category == "MOBILE":
                        pending = manager.pending_coop_requests.get(user_id)
                        if pending and (time.time() - pending.get("_ts", 0) < 60):
                            await websocket.send_text(
                                json.dumps(pending, ensure_ascii=False)
                            )
                    continue

                if msg_type == "BIOMETRIC_COOP_REQUEST":
                    data["sender_user_id"] = user_id
                    data["sender_username"] = username
                    data["_ts"] = time.time()

                    # 1) 요청자(user_id) 전용 대기열에 저장
                    manager.pending_coop_requests[user_id] = data

                    # 2) 요청자 본인의 MOBILE 소켓으로만 정밀 타겟 전송 (발신 데스크톱 자신 및 타 사원 제외)
                    await manager.send_to_user(
                        user_id=user_id,
                        message=data,
                        target_device="MOBILE",
                        exclude_ws=websocket,
                    )

                    # 3) 모바일 PWA가 백그라운드/슬립 상태일 때도 깨울 수 있도록 본인(user_id)에게만 Web Push 발송
                    try:
                        from domain.push.push_service import send_push_to_user

                        doc_title = data.get("docTitle", "대외비 문서")
                        asyncio.create_task(
                            asyncio.to_thread(
                                send_push_to_user,
                                user_id,
                                "🔐 [긴급] 중요 문서 지문 승인 요청",
                                f"데스크톱에서 '{doc_title}' 열람 지문 승인을 요청했습니다. 터치하여 지문을 인증해 주세요.",
                                "/v1/pages/device-test",
                            )
                        )
                    except Exception:
                        pass

                elif msg_type in ("BIOMETRIC_COOP_RESULT", "BIOMETRIC_COOP_CANCEL"):
                    data["sender_user_id"] = user_id
                    data["sender_username"] = username
                    data["_ts"] = time.time()

                    # 대기열 즉시 정리 후 요청자 본인의 다른 기기(데스크톱 등)로 결과/취소 신호 전달
                    manager.pending_coop_requests.pop(user_id, None)
                    await manager.send_to_user(
                        user_id=user_id,
                        message=data,
                        exclude_ws=websocket,
                    )
            except Exception:
                continue
    except WebSocketDisconnect:
        manager.disconnect(websocket)
