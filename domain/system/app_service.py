"""
============================================================================
[시스템 앱 레지스트리 및 자율 부트스트랩 서비스 (system/app_service.py)]
============================================================================

💡 이 파일의 역할:
- 시스템 관리자 앱(Admin Apps, `admin_*`) 17종의 메타데이터 및 초기 권한 정의
- 서버 기동 시 `app_registry` 테이블에 시스템 앱들을 멱등(Idempotent)하게 자동 등록
- 관리자가 `group-manage`에서 수정한 커스텀 권한(allow/deny_groups, min_rank)을 100% 보존
"""

import logging
from sqlalchemy.orm import Session
from models.system import AppRegistry

logger = logging.getLogger("app_service")

# 🏛️ 시스템 앱 18종 전수 정의 (app_id는 모두 admin_ 접두사 사용)
DEFAULT_SYSTEM_APPS = [
    {
        "app_id": "admin_dashboard",
        "name": "관리자 관제센터 대시보드",
        "title": "관리자 메인 종합 관제탑",
        "description": "시스템 자율신경계 태스크, 관제 통계 및 전사 앱 내비게이션 대시보드",
        "frontend_route": "/v1/admin",
        "icon_default": "mdi:view-dashboard-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_alerts",
        "name": "알림 관리",
        "title": "전사 알림 및 발송 관제",
        "description": "전사 공지 알림 발송, 알림 템플릿 관리 및 실시간 발송 이력 모니터링",
        "frontend_route": "/v1/admin/alerts",
        "icon_default": "mdi:bell-ring-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_media",
        "name": "미디어 관제",
        "title": "파일 자산 및 스토리지 관제",
        "description": "업로드된 미디어 자산 현황, 용량 모니터링 및 파일 무결성 관리",
        "frontend_route": "/v1/admin/media",
        "icon_default": "mdi:folder-multiple-image",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_target_groups",
        "name": "메시징 타겟 그룹",
        "title": "동적·정적 메시징 타겟 관리",
        "description": "오늘 근무자, 휴무자, 노선별 운전원 등 실시간 메시징 타겟 그룹 조회 및 갱신",
        "frontend_route": "/v1/admin/target-groups",
        "icon_default": "mdi:account-group-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_pushs",
        "name": "푸시 발송 관리",
        "title": "모바일 웹 푸시 발송",
        "description": "Web Push 구독자 대상 긴급 메시지 및 프로모션 푸시 발송",
        "frontend_route": "/v1/admin/pushs",
        "icon_default": "mdi:cellphone-message",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_dispatch",
        "name": "배차 운영 관리",
        "title": "일일 노선 배차표 관제",
        "description": "버스 노선별 일일 배차표 편성, 기사 배정 및 운행 확정 관리",
        "frontend_route": "/v1/admin/dispatch",
        "icon_default": "mdi:bus-clock",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_route_master",
        "name": "노선 마스터 관리",
        "title": "운행 노선 및 정류장 마스터",
        "description": "시내/시외 버스 노선, 정류장 경유지 및 정기 운행 시간표 관리",
        "frontend_route": "/v1/admin/route_master",
        "icon_default": "mdi:map-marker-path",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_dayoff",
        "name": "근태·휴무 관리",
        "title": "기사 연차 및 휴무 승인 관제",
        "description": "운전원 근태 및 연차/휴무 신청 접수, 승인·반려 및 캘린더 관리",
        "frontend_route": "/v1/admin/dayoff",
        "icon_default": "mdi:calendar-account-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_boards",
        "name": "게시판 마스터 관리",
        "title": "전사 게시판 인스턴스 설정",
        "description": "사내 게시판 생성, 슬러그 지정 및 게시판별 읽기/쓰기 랭크 설정",
        "frontend_route": "/v1/admin/boards",
        "icon_default": "mdi:clipboard-text-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_pages",
        "name": "페이지 빌더 관리",
        "title": "정적/동적 안내 페이지 빌더",
        "description": "공지성 고정 페이지, 회사 소개, 이용약관 등 정적 페이지 관리",
        "frontend_route": "/v1/admin/pages",
        "icon_default": "mdi:file-document-edit-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_observability",
        "name": "통합 관제 & 감사로그",
        "title": "보안 침해 및 실시간 세션 관제",
        "description": "실시간 사용자 세션 추적, 악성 세션 강제 킥아웃 및 보안/에러 감사로그 분석",
        "frontend_route": "/v1/admin/observability",
        "icon_default": "mdi:shield-alert-outline",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_user_manage",
        "name": "사용자·직급 관리",
        "title": "계정 승강 및 직급/그룹 지정",
        "description": "신규 사원 계정 발급, 권한 랭크 승강(Lv.0~9) 및 주/부그룹 편성",
        "frontend_route": "/v1/admin/user-manage",
        "icon_default": "mdi:account-cog-outline",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_group_manage",
        "name": "조직·권한 통제소",
        "title": "주/부그룹 마스터 및 인스턴스 권한 배분",
        "description": "조직 주/부그룹 코드 관리, 비즈니스 인스턴스 및 시스템 앱 권한 배분 관제",
        "frontend_route": "/v1/admin/group-manage",
        "icon_default": "mdi:shield-account-outline",
        "min_read_rank": 9,
        "min_write_rank": 9,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_tasks",
        "name": "태스크 & 크론 워커",
        "title": "자율신경계 비동기 태스크 스케줄러",
        "description": "백그라운드 비동기 태스크 큐 및 자율 주기 Cron 스케줄러 상태 모니터링/제어",
        "frontend_route": "/v1/admin/tasks",
        "icon_default": "mdi:robot-industrial",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_config",
        "name": "시스템 환경설정",
        "title": "전역 시스템 설정 및 Watchdog 경보",
        "description": "시스템 캐시/세션 보존 주기(GC) 및 실시간 이상 징후 자동 경보(Watchdog) 기준 설정",
        "frontend_route": "/v1/admin/config",
        "icon_default": "mdi:tune-vertical",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_apps",
        "name": "앱 레지스트리 관리",
        "title": "플러그인 및 앱 등록 마스터",
        "description": "플러그인 및 신규 애플리케이션 등록, 메타데이터 스키마 관리",
        "frontend_route": "/v1/admin/apps",
        "icon_default": "mdi:apps-box",
        "min_read_rank": 9,
        "min_write_rank": 9,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_menu",
        "name": "메뉴 트리 관리",
        "title": "내비게이션 메뉴 구조 관리",
        "description": "사이드바 및 글로벌 내비게이션 메뉴 트리 구조 및 노출 권한 관리",
        "frontend_route": "/v1/admin/menu",
        "icon_default": "mdi:menu-open",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_services",
        "name": "마이크로서비스 엔진",
        "title": "레고형 마이크로서비스 엔진 레지스트리",
        "description": "댓글, 첨부파일 등 마이크로서비스 엔진 조립 및 서비스 인스턴스 제어",
        "frontend_route": "/v1/admin/services",
        "icon_default": "mdi:toy-brick-outline",
        "min_read_rank": 9,
        "min_write_rank": 9,
        "allow_groups": [],
        "deny_groups": [],
    },
]


def bootstrap_system_apps(db: Session) -> dict:
    """
    [시스템 앱 자율 부트스트랩 엔진]
    - DB에 없는 17종 시스템 앱(`admin_*`)을 멱등(Idempotent)하게 자동 등록합니다.
    - 기존에 등록된 앱은 건너뛰어, 관리자가 설정한 커스텀 권한(allow/deny_groups, 랭크)을 보존합니다.
    """
    created_count = 0
    skipped_count = 0

    for app_meta in DEFAULT_SYSTEM_APPS:
        existing = db.query(AppRegistry).filter(AppRegistry.app_id == app_meta["app_id"]).first()
        if existing:
            skipped_count += 1
            continue

        new_app = AppRegistry(
            app_id=app_meta["app_id"],
            name=app_meta["name"],
            title=app_meta["title"],
            description=app_meta["description"],
            app_type="SYSTEM",
            frontend_route=app_meta["frontend_route"],
            icon_default=app_meta["icon_default"],
            min_read_rank=app_meta["min_read_rank"],
            min_write_rank=app_meta["min_write_rank"],
            allow_groups=app_meta["allow_groups"],
            deny_groups=app_meta["deny_groups"],
            is_active=True,
        )
        db.add(new_app)
        created_count += 1

    if created_count > 0:
        db.commit()
        logger.info(f"✨ [AppService] 시스템 앱 {created_count}개 자동 등록 완료 (기존 {skipped_count}개 보존)")
    else:
        logger.info(f"🛡️ [AppService] 시스템 앱 {len(DEFAULT_SYSTEM_APPS)}개 모두 최신 상태 유지 (변경 없음)")

    return {
        "created": created_count,
        "skipped": skipped_count,
        "total": len(DEFAULT_SYSTEM_APPS)
    }
