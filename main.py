import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from domain.question import question_router
from domain.answer import answer_router
from domain.user import user_router
from domain.fileupload import fileupload_router
from domain.media import media_router
from domain.dayoff import dayoff_router
from domain.push import push_router
from domain.alert import alert_router
from domain.ws import ws_router, ws_service
from domain.system.task_worker import run_task_worker # [v1.6.0] 시스템 워커 임포트

from database import engine
from models import Base
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- [Startup] 애플리케이션 시작 시 ---
    
    # 1. 웹소켓 실시간 연결 유지(Ping) 루프 시작
    ping_task = asyncio.create_task(ws_service.ping_loop())
    
    # 2. 시스템 비동기 태스크 워커 가동 (자율 신경계 시작)
    # 이 워커는 DB를 감시하며 삭제, 이메일, 스케줄 작업 등을 뒤에서 묵묵히 처리합니다.
    system_task_worker = asyncio.create_task(run_task_worker())
    
    yield
    
    # --- [Shutdown] 애플리케이션 종료 시 ---
    
    # 3. 가동 중인 백그라운드 작업들 안전하게 종료 요청 (Graceful Shutdown)
    ping_task.cancel()
    system_task_worker.cancel()
    
    # 작업들이 완전히 멈출 때까지 기다려줍니다.
    await asyncio.gather(ping_task, system_task_worker, return_exceptions=True)
    print("👋 시스템 워커가 안전하게 종료되었습니다.")

from domain.v1.board import board_router as v1_board_router
from domain.v1.admin import admin_router as v1_admin_router
from domain.v1.admin import group_router as admin_group_router
from domain.v1.admin import auth_group_router # [조직/권한 그룹 마스터 라우터]
from domain.v1.admin import observability_router # [통합 관제 및 감사로그 라우터]
from domain.v1.admin import task_admin_router # [v1.6.0] 관리자 태스크 라우터 임포트
from domain.v1.miniapp import miniapp_router # [미니앱 통합 액션 피드 라우터]
from domain.v1.app import app_router as v1_app_router
from domain.v1.custom import custom_router as v1_custom_router
from domain.v1.comment import comment_router
from domain.page import page_router

app = FastAPI(lifespan=lifespan)

# 정적 파일(이미지 등) 서빙 설정
# [v1.6.0] 보안 표준에 따라 전체 /uploads 마운트 제거. 
# 공개 자산은 Nginx의 /public/ 경로를 통해 직접 서빙되며, 
# 보안 자산은 API를 통한 X-Accel-Redirect 방식으로만 접근 가능함.
# upload_dir = os.getenv("UPLOAD_DIR", "uploads")
# os.makedirs(upload_dir, exist_ok=True)
# app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

from core.config import settings
from core.exceptions import CoreException
from core.middleware import RequestIDMiddleware
from core.audit import safe_log_audit
from core.session import validate_session
from database import SessionLocal
from fastapi import Request
from fastapi.responses import JSONResponse
import traceback
from datetime import datetime

# 📌 [전역 예외 핸들러 1] CoreException 표준 처리 및 403 보안 침해 / 500 에러 자동 감사로그 포획
@app.exception_handler(CoreException)
async def core_exception_handler(request: Request, exc: CoreException):
    req_id = getattr(request.state, "request_id", None)
    ip = request.client.host if request.client else "unknown"

    # 세션 쿠키에서 유저 식별 (감사로그 행위자 파악)
    session_id = request.cookies.get("session_id")
    user = None
    if session_id:
        try:
            with SessionLocal() as db:
                user = validate_session(db, session_id)
        except Exception:
            pass

    # 🚨 403 권한 침해 시 즉시 SECURITY 감사로그 적재
    if exc.status_code == 403:
        with SessionLocal() as db:
            safe_log_audit(
                db=db,
                app_id=exc.resource or "system",
                log_type="SECURITY",
                severity="WARN",
                action="ACCESS_DENIED",
                title=f"403 권한 침해 차단: {request.method} {request.url.path}",
                user=user,
                resource_type=exc.resource,
                message=exc.message,
                ip_address=ip,
                metadata={
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error_code": exc.code,
                }
            )
    elif exc.status_code >= 500:
        with SessionLocal() as db:
            safe_log_audit(
                db=db,
                app_id=exc.resource or "system",
                log_type="ERROR",
                severity="ERROR",
                action="CORE_EXCEPTION",
                title=f"500 코어 서버 장애: {request.method} {request.url.path}",
                user=user,
                resource_type=exc.resource,
                message=exc.message,
                ip_address=ip,
                metadata={
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error_code": exc.code,
                }
            )

    resp = exc.to_response()
    if req_id:
        resp.headers["X-Request-ID"] = req_id
    return resp


# 📌 [전역 예외 핸들러 2] 처리되지 않은 미처리 500 서버 장애 자동 캡처 (스택 트레이스 영구 보존)
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", None)
    ip = request.client.host if request.client else "unknown"
    stack_trace = traceback.format_exc()

    session_id = request.cookies.get("session_id")
    user = None
    if session_id:
        try:
            with SessionLocal() as db:
                user = validate_session(db, session_id)
        except Exception:
            pass

    with SessionLocal() as db:
        safe_log_audit(
            db=db,
            app_id="system",
            log_type="ERROR",
            severity="CRITICAL",
            action="UNHANDLED_EXCEPTION",
            title=f"500 미처리 서버 장애: {request.method} {request.url.path}",
            user=user,
            message=f"{str(exc)}\n\n[스택 트레이스]:\n{stack_trace}",
            ip_address=ip,
            metadata={
                "request_id": req_id,
                "method": request.method,
                "path": request.url.path,
                "exception_type": exc.__class__.__name__,
            }
        )

    headers = {}
    if req_id:
        headers["X-Request-ID"] = req_id

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "status": 500,
                "message": "서버 내부 처리 중 예기치 못한 장애가 발생했습니다.",
                "request_id": req_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        },
        headers=headers
    )

# 📌 [미들웨어 등록 1] X-Request-ID 상관관계 추적 미들웨어 (모든 요청에 고유 추적 ID 발급)
app.add_middleware(RequestIDMiddleware)

# 📌 [미들웨어 등록 2] CORS 설정 (중앙 설정소 core/config.py 목록 적용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/hello")
async def root():
    return {"message": "Hello World!!"}

app.include_router(question_router.router)
app.include_router(answer_router.router)
app.include_router(user_router.router)
app.include_router(fileupload_router.router)
app.include_router(media_router.router)
app.include_router(dayoff_router.router)
app.include_router(push_router.router)
app.include_router(alert_router.router)
app.include_router(ws_router.router)
app.include_router(v1_board_router.router)
app.include_router(v1_admin_router.router, prefix="/v1")
app.include_router(admin_group_router.router)
app.include_router(auth_group_router.router)
app.include_router(observability_router.router) # [통합 관제 및 감사로그 라우터]
app.include_router(miniapp_router.router) # [전사 통합 미니앱 마이크로 텍스트 엔진]
app.include_router(task_admin_router.router, prefix="/v1") # /api/v1/admin/tasks 로 등록
app.include_router(v1_app_router.router)
app.include_router(v1_custom_router.router)
app.include_router(comment_router.router)
app.include_router(page_router.router)






def main():
    """
    main test Document

    
    """
    print("Hello from test!")


if __name__ == "__main__":
    main()
