import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

# 🖥️ 시스템 콘솔 원시 로그(Raw System Log) 영구 보존용 파일 핸들러 설정 (최대 10MB, 백업 5개)
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
SYSTEM_LOG_PATH = os.path.join(LOG_DIR, "system.log")

system_file_handler = RotatingFileHandler(
    SYSTEM_LOG_PATH,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)
system_file_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
system_file_handler.setFormatter(system_file_formatter)

# 루트 로거 및 uvicorn 로거에 바인딩
root_logger = logging.getLogger()
if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
    root_logger.addHandler(system_file_handler)
    logging.getLogger("uvicorn").addHandler(system_file_handler)
    logging.getLogger("uvicorn.access").addHandler(system_file_handler)
    logging.getLogger("uvicorn.error").addHandler(system_file_handler)
    logging.getLogger("fastapi").addHandler(system_file_handler)

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
    
    # 0. 자율신경계 필수 정기 태스크 및 시스템 앱 자동 시드 (Bootstrap)
    try:
        from sqlalchemy import inspect as sa_inspect, text as sa_text
        from database import SessionLocal
        from models.miniapp import MiniappRead
        from models.dayoff import DayOffPolicy
        # 📌 [방안 B] 미니앱 1:N 확인 서명 및 휴무 정책 이력 테이블 자동 보증
        MiniappRead.__table__.create(bind=engine, checkfirst=True)
        DayOffPolicy.__table__.create(bind=engine, checkfirst=True)
        existing_policy_cols = {c["name"] for c in sa_inspect(engine).get_columns("dayoff_policy")}
        with engine.begin() as conn:
            for col_name in ("min_advance_days", "max_advance_days"):
                if col_name not in existing_policy_cols:
                    conn.execute(sa_text(f"ALTER TABLE dayoff_policy ADD COLUMN {col_name} INTEGER NOT NULL DEFAULT 0"))

        from domain.system.task_service import bootstrap_default_cron_tasks
        from domain.system.app_service import bootstrap_system_apps
        from core.audit import register_security_audit_hook
        from domain.system.watchdog_service import check_and_alert_security_violation

        # 🛡️ 코어 보안 감사로그 - Watchdog 리스너 훅 등록
        register_security_audit_hook(check_and_alert_security_violation)

        with SessionLocal() as db:
            from domain.dayoff.dayoff_crud import ensure_initial_dayoff_policy
            ensure_initial_dayoff_policy(db)
            seeded = bootstrap_default_cron_tasks(db)
            if seeded > 0:
                print(f"🌱 자율신경계 필수 정기 태스크 {seeded}건이 성공적으로 등록되었습니다.")
            app_seed = bootstrap_system_apps(db)
            if app_seed["created"] > 0:
                print(f"✨ 시스템 앱 {app_seed['created']}건이 성공적으로 등록되었습니다.")
            
            # 🧹 [과거 레거시 정화] 관제 분리 원칙에 따라 피드 내 과거 보안 경보 레코드 안전 삭제
            from models.miniapp import MiniappItem
            cleaned_alarms = db.query(MiniappItem).filter(
                MiniappItem.title.like("%보안 경보%")
            ).delete(synchronize_session=False)
            if cleaned_alarms > 0:
                db.commit()
                print(f"🧹 피드 내 레거시 보안 경보 레코드 {cleaned_alarms}건이 영구 정화되었습니다.")
    except Exception as e:
        print(f"⚠️ 시스템 부트스트랩 오류: {e}")

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
    await ws_service.manager.close_all()
    
    # 작업들이 완전히 멈출 때까지 기다려줍니다.
    await asyncio.gather(ping_task, system_task_worker, return_exceptions=True)
    print("👋 시스템 워커 및 실시간 웹소켓 연결이 안전하게 종료되었습니다.")

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
from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback
from datetime import datetime

# 📌 [전역 예외 핸들러 1] CoreException 표준 처리 및 403 보안 침해 / 500 에러 자동 감사로그 포획
@app.exception_handler(CoreException)
async def core_exception_handler(request: Request, exc: CoreException):
    req_id = getattr(request.state, "request_id", None)
    ip = request.client.host if request.client else "unknown"
    session_id = request.cookies.get("session_id")

    # 🚨 단일 DB 세션에서 유저 검증 및 403/500 감사로그를 원자적으로 처리 (Fail-Safe 격리)
    try:
        with SessionLocal() as db:
            user = None
            if session_id:
                try:
                    user = validate_session(db, session_id)
                except Exception:
                    pass

            error_code_val = getattr(exc, "error_code", getattr(exc, "code", "UNKNOWN_ERROR"))

            if exc.status_code == 403:
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
                        "error_code": error_code_val,
                    }
                )
            elif exc.status_code >= 500:
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
                        "error_code": error_code_val,
                    }
                )
    except Exception as log_err:
        # 감사로그 로깅 도중 예외가 발생하더라도 원래 예외 응답(403 등)은 500으로 마스킹되지 않고 반드시 정상 반환
        pass

    resp = exc.to_response()
    if req_id:
        resp.headers["X-Request-ID"] = req_id
    return resp


# 📌 [전역 예외 핸들러 2] Starlette/FastAPI HTTPException 표준 포획 (403 감사로그 100% 누락 방어)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", None)
    ip = request.client.host if request.client else "unknown"
    session_id = request.cookies.get("session_id")

    with SessionLocal() as db:
        user = None
        if session_id:
            try:
                user = validate_session(db, session_id)
            except Exception:
                pass

        # 🚨 403 권한 거부 시 무조건 SECURITY 감사로그 자동 박제
        if exc.status_code == 403:
            safe_log_audit(
                db=db,
                app_id="system",
                log_type="SECURITY",
                severity="WARN",
                action="ACCESS_DENIED",
                title=f"403 권한 침해 차단: {request.method} {request.url.path}",
                user=user,
                resource_type="system",
                message=str(exc.detail),
                ip_address=ip,
                metadata={
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 403,
                }
            )
        elif exc.status_code >= 500:
            safe_log_audit(
                db=db,
                app_id="system",
                log_type="ERROR",
                severity="ERROR",
                action="HTTP_ERROR",
                title=f"500 서버 장애: {request.method} {request.url.path}",
                user=user,
                resource_type="system",
                message=str(exc.detail),
                ip_address=ip,
                metadata={
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": exc.status_code,
                }
            )

    headers = getattr(exc, "headers", None) or {}
    if req_id:
        headers["X-Request-ID"] = req_id

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}},
        headers=headers
    )


# 📌 [전역 예외 핸들러 2] 처리되지 않은 미처리 500 서버 장애 자동 캡처 (스택 트레이스 영구 보존)
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", None)
    ip = request.client.host if request.client else "unknown"
    stack_trace = traceback.format_exc()

    session_id = request.cookies.get("session_id")
    try:
        with SessionLocal() as db:
            user = None
            if session_id:
                try:
                    user = validate_session(db, session_id)
                except Exception:
                    pass

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
    except Exception as log_err:
        pass

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
                "timestamp": datetime.now().isoformat(),
            },
            # 🌟 프론트엔드 레거시 파서(err.detail) 하위 호환성을 위해 최상위 detail 제공
            "detail": "서버 내부 처리 중 예기치 못한 장애가 발생했습니다.",
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
