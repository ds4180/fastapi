"""
============================================================================
[코어 HTTP 요청 상관관계(Correlation ID) 미들웨어 (core/middleware.py)]
============================================================================

💡 이 파일의 역할:
시스템으로 들어오는 모든 HTTP 요청에 고유한 추적 식별자(X-Request-ID)를 발급하여,
프론트엔드 에러 리포트와 백엔드 감사로그를 1초 만에 1:1로 대조(Correlation)할 수 있게 합니다.

🌟 엔터프라이즈 운영 핵심 이점:
1. [초고속 장애 색인]: 프론트 화면에 "요청 ID: req_a1b2c3d4"를 띄우고, 관리자가 로그 관제탑에서 해당 ID로 검색하면 단 0.01초 만에 원인 규명 완료!
2. [전 구간 추적성 (End-to-End Tracing)]: 요청 진입부터 세션 검증, 권한 판별, 비즈니스 처리, 감사로그 적재까지 동일한 ID가 공유됩니다.
"""

import uuid
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    [X-Request-ID 발급 및 상관관계 추적 미들웨어]
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. 클라이언트(Nginx 또는 프론트엔드)가 이미 X-Request-ID를 보냈다면 재사용하고,
        #    없다면 고유한 12자리 식별자('req_' + 12자리 hex)를 새로 발급합니다.
        incoming_id = request.headers.get("X-Request-ID")
        request_id = incoming_id if incoming_id else f"req_{uuid.uuid4().hex[:12]}"

        # 2. 요청 상태 주머니(request.state)에 바인딩하여 라우터 및 감사로그에서 참조 가능하게 함
        request.state.request_id = request_id
        request.state.start_time = time.time()

        # 3. 다음 미들웨어 및 실제 API 라우터 실행
        response: Response = await call_next(request)

        # 🛡️ [슬라이딩 윈도우 브라우저 쿠키 동기화]
        # 활동 임계치(5분) 도달로 last_activity가 갱신된 HTTP 요청에만 브라우저 쿠키 Max-Age를 재발급합니다.
        renew_jti = getattr(request.state, "renew_session_id", None)
        if (
            renew_jti
            and response.status_code < 400
            and not getattr(request.state, "session_terminated", False)
        ):
            set_cookie_headers = (
                response.headers.getlist("set-cookie")
                if hasattr(response.headers, "getlist")
                else [response.headers.get("set-cookie", "")]
            )
            has_session_cookie = any("session_id=" in h for h in set_cookie_headers if h)
            if not has_session_cookie:
                from core.session import SESSION_EXPIRE_SECONDS

                response.set_cookie(
                    key="session_id",
                    value=renew_jti,
                    httponly=True,
                    max_age=SESSION_EXPIRE_SECONDS,
                    samesite="lax",
                    secure=False,
                    path="/",
                )

        # 4. 응답 헤더에 X-Request-ID를 탑재하여 브라우저에 회신
        response.headers["X-Request-ID"] = request_id

        # 5. 응답 시간(Latency ms) 계산 및 헤더 주입
        elapsed_ms = round((time.time() - request.state.start_time) * 1000, 2)
        response.headers["X-Response-Time"] = f"{elapsed_ms}ms"

        return response
