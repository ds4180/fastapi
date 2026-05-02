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
from domain.v1.admin import task_admin_router # [v1.6.0] 관리자 태스크 라우터 임포트
from domain.v1.app import app_router as v1_app_router
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

# 기본 허용 주소 목록
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://localhost",
]

# 환경 변수 ALLOW_ORIGINS가 있으면 목록에 추가합니다. (쉼표로 구분하여 여러 개 추가 가능)
env_origins = os.getenv("ALLOW_ORIGINS")
if env_origins:
    # "http://192.168.200.217,http://bus1942.com" 같은 문자열을 리스트로 변환
    origins.extend([origin.strip() for origin in env_origins.split(",")])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
app.include_router(task_admin_router.router, prefix="/v1") # /api/v1/admin/tasks 로 등록
app.include_router(v1_app_router.router)
app.include_router(comment_router.router)
app.include_router(page_router.router)






def main():
    """
    main test Document

    
    """
    print("Hello from test!")


if __name__ == "__main__":
    main()
