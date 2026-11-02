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

# 🏛️ 시스템 앱 18종 전수 정의 (app_id는 모두 admin_ 접두사 사용, /admin/+page.svelte 공식 명칭과 완전 동기화)
DEFAULT_SYSTEM_APPS = [
    {
        "app_id": "admin_dashboard",
        "name": "매니져 페이지",
        "title": "매니져 페이지",
        "description": "시스템 전체 현황 통계, 시스템 코어 및 비즈니스 앱 통합 관제탑",
        "frontend_route": "/v1/admin",
        "icon_default": "mdi:view-dashboard-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_alerts",
        "name": "알림·지시 관리",
        "title": "알림·지시 관리",
        "description": "전역/경로별 상단 공지 배너 및 중앙 모달 알림 생성·배포 (운영 위임 가능)",
        "frontend_route": "/v1/admin/alerts",
        "icon_default": "mdi:bell-cog-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_media",
        "name": "파일·사진 관리",
        "title": "파일·사진 관리",
        "description": "전체 업로드 파일 자산 모니터링 및 스토리지 용량 관리 (운영 위임 가능)",
        "frontend_route": "/v1/admin/media",
        "icon_default": "mdi:database-cog-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_target_groups",
        "name": "임시 그룹 관리",
        "title": "임시 그룹 관리",
        "description": "알림·메시지 발송을 위한 기사 노선별/직급별 동적 그룹 필터링 및 연산",
        "frontend_route": "/v1/admin/target-groups",
        "icon_default": "mdi:bullhorn-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_pushs",
        "name": "푸시·구독 관리",
        "title": "푸시·구독 관리",
        "description": "모바일/PC Web Push 활성 구독 기기 현황 모니터링, 무효 구독 정리 및 전사 푸시 발송",
        "frontend_route": "/v1/admin/pushs",
        "icon_default": "mdi:cellphone-message",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_dispatch",
        "name": "차량 배차 관리",
        "title": "차량 배차 관리",
        "description": "실시간 노선별 차량 투입, 기사 배정 및 일일 운행 시간표 조율",
        "frontend_route": "/v1/admin/dispatch",
        "icon_default": "mdi:bus-multiple",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_route_master",
        "name": "노선 마스터 관리",
        "title": "노선 마스터 관리",
        "description": "정규 및 임시 노선의 기준 버전 도면 및 회차 시간표 통합 관리 (배차 앱 연동)",
        "frontend_route": "/v1/admin/route_master",
        "icon_default": "mdi:bus-clock",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_dayoff",
        "name": "휴무(결근계) 관리",
        "title": "휴무(결근계) 관리",
        "description": "직원 및 승무원의 연차/휴무 신청 내역 승인·반려 관제",
        "frontend_route": "/v1/admin/dayoff",
        "icon_default": "mdi:calendar-check-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_boards",
        "name": "게시판 인스턴스 관리",
        "title": "게시판 인스턴스 관리",
        "description": "추상화 다중 게시판(공지, 자유 등) 슬러그 생성 및 레이아웃 정책 설정",
        "frontend_route": "/v1/admin/boards",
        "icon_default": "mdi:clipboard-text-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_pages",
        "name": "페이지 엔진 관리",
        "title": "페이지 엔진 관리",
        "description": "DB 기반 고정 콘텐츠 다중 페이지 인스턴스 생성 및 게시 기간 제어",
        "frontend_route": "/v1/admin/pages",
        "icon_default": "mdi:file-document-edit-outline",
        "min_read_rank": 4,
        "min_write_rank": 4,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_observability",
        "name": "접속 기록·감사 로그",
        "title": "접속 기록·감사 로그",
        "description": "실시간 세션 추적·강제추방, 4대 감사로그(접근/도메인Diff/장애/보안) 전사 관제",
        "frontend_route": "/v1/admin/observability",
        "icon_default": "mdi:shield-check-outline",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_user_manage",
        "name": "사용자 랭크 관리",
        "title": "사용자 랭크 관리",
        "description": "회원 권한 등급(rank_level 0~9) 조정 및 주그룹/부그룹 소속 관리",
        "frontend_route": "/v1/admin/user-manage",
        "icon_default": "mdi:account-group-outline",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_group_manage",
        "name": "그룹·권한 관리",
        "title": "그룹·권한 관리",
        "description": "주/부그룹 마스터 및 인스턴스/시스템 앱 독립 권한 배분 관제탑",
        "frontend_route": "/v1/admin/group-manage",
        "icon_default": "mdi:shield-account-outline",
        "min_read_rank": 9,
        "min_write_rank": 9,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_tasks",
        "name": "예약 작업 관리",
        "title": "예약 작업 관리",
        "description": "비동기 백그라운드 작업 큐 상태 모니터링 및 자율신경계 스케줄러 제어",
        "frontend_route": "/v1/admin/tasks",
        "icon_default": "mdi:robot-industrial",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_config",
        "name": "환경설정",
        "title": "환경설정",
        "description": "글로벌 환경 변수, 데이터 보존 주기(GC) 및 Watchdog 이상 경보 제어",
        "frontend_route": "/v1/admin/config",
        "icon_default": "mdi:tune-vertical",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_apps",
        "name": "앱 설치 등록",
        "title": "앱 설치 등록",
        "description": "INSTANCE / CUSTOM / SYSTEM 앱 엔진 등록 및 메타데이터·권한 관리",
        "frontend_route": "/v1/admin/apps",
        "icon_default": "mdi:apps",
        "min_read_rank": 9,
        "min_write_rank": 9,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_menu",
        "name": "메뉴 설정",
        "title": "메뉴 설정",
        "description": "시스템 전체 내비게이션 트리 및 앱 연결·접근 권한 구조 편집",
        "frontend_route": "/v1/admin/menu",
        "icon_default": "mdi:menu-open",
        "min_read_rank": 8,
        "min_write_rank": 8,
        "allow_groups": [],
        "deny_groups": [],
    },
    {
        "app_id": "admin_services",
        "name": "서비스 마스터 (Add-on)",
        "title": "서비스 마스터 (Add-on)",
        "description": "INSTANCE 및 CUSTOM 앱에 애드온(Add-on) 결합하는 레고형 서비스 번들 관리",
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
    - DB에 없는 18종 시스템 앱(`admin_*`)을 멱등(Idempotent)하게 자동 등록합니다.
    - 기존에 등록된 앱의 아이콘 및 공식 명칭(title, name, description)을 안전하게 동기화합니다.
    """
    created_count = 0
    updated_count = 0
    skipped_count = 0

    for app_meta in DEFAULT_SYSTEM_APPS:
        existing = db.query(AppRegistry).filter(AppRegistry.app_id == app_meta["app_id"]).first()
        if existing:
            updated = False
            # 기본 아이콘이 변경된 경우 안전하게 동기화 보정
            if app_meta.get("icon_default") and existing.icon_default != app_meta["icon_default"]:
                existing.icon_default = app_meta["icon_default"]
                updated = True
            # 제목(title) 또는 명칭(name)이 변경된 경우 동기화 보정
            if app_meta.get("title") and existing.title != app_meta["title"]:
                existing.title = app_meta["title"]
                updated = True
            if app_meta.get("name") and existing.name != app_meta["name"]:
                existing.name = app_meta["name"]
                updated = True
            if app_meta.get("description") and existing.description != app_meta["description"]:
                existing.description = app_meta["description"]
                updated = True

            if updated:
                db.commit()
                updated_count += 1
            else:
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

    if created_count > 0 or updated_count > 0:
        db.commit()
        logger.info(f"✨ [AppService] 시스템 앱 {created_count}개 생성, {updated_count}개 타이틀 동기화 완료 (기존 {skipped_count}개 유지)")
    else:
        logger.info(f"🛡️ [AppService] 시스템 앱 {len(DEFAULT_SYSTEM_APPS)}개 모두 최신 상태 유지 (변경 없음)")

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "total": len(DEFAULT_SYSTEM_APPS)
    }
