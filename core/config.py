"""
============================================================================
[백엔드 중앙 환경변수 및 시스템 설정 모듈 (core/config.py)]
============================================================================

💡 이 파일의 역할:
시스템 곳곳(DB 접속, Redis, 파일 경로, 비밀키 등)에 흩어져 있던 `os.getenv(...)` 호출을
하나의 안전하고 명확한 '중앙 관제소'로 모았습니다.

🌟 장점:
1. 어떤 앱(시스템 앱, 배차, 게시판 등)이 새로 추가되더라도 `from core.config import settings`
   한 줄이면 시스템의 모든 핵심 설정값을 안전하게 조회할 수 있습니다.
2. 타입 힌팅과 기본값을 제공하여 환경변수 오타나 누락으로 인한 런타임 오류를 원천 차단합니다.
3. `.env` 파일이 존재할 경우 자동으로 읽어들여 개발/프로덕션 환경을 유연하게 전환합니다.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# ----------------------------------------------------------------------------
# 1. .env 파일 자동 탐색 및 로드
# ----------------------------------------------------------------------------
# test/.env 또는 프로젝트 루트(.env) 파일이 있으면 자동으로 환경변수로 등록합니다.
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
ROOT_DIR = PROJECT_DIR.parent

# 1순위: test/.env, 2순위: 루트/.env
if (PROJECT_DIR / ".env").exists():
    load_dotenv(PROJECT_DIR / ".env")
elif (ROOT_DIR / ".env").exists():
    load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """
    시스템 전역 불변(frozen) 설정 클래스
    실수로 코드 내에서 설정값이 변경되는 사고를 막기 위해 frozen=True 로 고정합니다.
    """

    # 📌 [1] 시스템 기본 메타데이터
    PROJECT_NAME: str = "Jeju.live Core Platform"
    VERSION: str = "2.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # 📌 [2] 데이터베이스 접속 주소 (PostgreSQL)
    # 도커 내부망에서는 호스트명 'db'를 사용합니다.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+psycopg://lee:1234@db:5432/bus_db"
    )

    # 📌 [3] Redis 실시간 캐시 및 멀티 디바이스 세션 설정
    # 도커 내부망에서는 서비스명 'redis'로 접근합니다.
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "1234")

    # 📌 [4] 보안 및 암호화 키
    # 세션 검증 및 보안 토큰 서명에 사용되는 32바이트 이상의 비밀키
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", 
        "cceb75393b383115054b2195c59b3d4a5a948c8c530182855f0610b6a59083ad"
    )
    # 세션 만료 기간 (일 단위) - 기본 3일
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "3"))

    # 🛡️ [4-1] 로그인 보안 및 쿠키 정책 설정 (Brute-Force 방어 & HTTPS 쿠키 제어)
    # - COOKIE_SECURE: HTTPS 운영 환경에서는 True로 설정하여 평문(HTTP) 쿠키 전송을 차단합니다.
    #   (내부 HTTP 프록시/로컬 개발 환경 호환을 위해 기본값은 False)
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1", "t")
    # - 계정+IP 기준 연속 로그인 실패 허용 횟수 (기본 5회 실패 시 300초=5분 잠금)
    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_SECONDS: int = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "300"))
    # - 단일 IP 기준 무차별 대입(다중 계정 스캐닝) 허용 횟수 (기본 15회 실패 시 900초=15분 잠금)
    LOGIN_IP_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_IP_MAX_ATTEMPTS", "15"))
    LOGIN_IP_LOCKOUT_SECONDS: int = int(os.getenv("LOGIN_IP_LOCKOUT_SECONDS", "900"))

    # 📌 [5] 파일 및 미디어 저장소 경로
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/app/uploads")
    # 파일 업로드 크기 제한 (기본 100MB)
    BODY_SIZE_LIMIT: int = int(os.getenv("BODY_SIZE_LIMIT", "104857600"))

    # 📌 [6] CORS (교차 출처 리소스 공유) 허용 도메인 목록
    ALLOW_ORIGINS: List[str] = field(default_factory=lambda: [
        origin.strip()
        for origin in os.getenv(
            "ALLOW_ORIGINS", 
            "https://jeju.live,https://dev.jeju.live,http://localhost:5173,http://localhost:3000,http://localhost"
        ).split(",")
        if origin.strip()
    ])

    # 📌 [7] 웹 푸시 알림 (VAPID) 키
    VAPID_PUBLIC_KEY: str = os.getenv(
        "VAPID_PUBLIC_KEY", 
        "BFo_ZVqvUj1h1Z-wRRsHn9-uJecPXcPqGnDNfEuy6-H16ax9-H_-JTyAH_9gEyLQTD_yxv5dB3cupfG2SCSk62A"
    )
    VAPID_PRIVATE_KEY: str = os.getenv(
        "VAPID_PRIVATE_KEY", 
        "4pEtY2AYOArlBnYTWlv8-w8pRS21VhiQCZHD2rwUH74"
    )
    VAPID_SUBJECT: str = os.getenv("VAPID_SUBJECT", "mailto:admin@jeju.live")


# ============================================================================
# 어디서든 `from core.config import settings` 로 가져다 쓸 수 있는 전역 인스턴스
# ============================================================================
settings = Settings()
