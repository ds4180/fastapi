# 📑 메뉴 인텔리전스 및 주소 체계 통합 작업 레포트 (v1.5.10)

## 1. 개요
본 작업은 시스템 내의 다양한 앱(게시판, 페이지, 휴무계 등)의 메뉴 내비게이션 환경을 통합하고, 관리자 전용 메뉴 생성을 상시 지원하기 위해 진행되었습니다.

---

## 2. 백엔드 개선 사항 ([admin_router.py](file:///home/lee/uv-code/test/domain/v1/admin/admin_router.py))

### 🌐 주소 체계 표준화 (DRY 원칙 적용)
*   **상수 도입**: `/v1/admin`, `/v1/app` 등 하드코딩된 경로를 파일 상단에 `ADMIN_PREFIX`, `APP_PREFIX` 상수로 정의하여 유지보수성을 극대화했습니다. 
*   **라우터 통합**: `APIRouter` 정의 시에도 이 상수를 참조하게 하여 시스템 주소 체계의 일관성을 확보했습니다.

### 🧠 지능형 메뉴 URL 해석기 ([resolve_menu_url](file:///home/lee/uv-code/test/domain/v1/admin/admin_router.py#150-200)) 고도화
*   **관리자 모드 전용 인스턴스 ID (-1) 지원**:
    *   메뉴 등록 시 `app_instance_id`가 `-1`로 설정된 경우, 앱 종류(STATIC/INSTANCE)에 관계없이 즉시 해당 앱의 **최상위 관리 도구 페이지** 주소를 반환합니다.
    *   반환 형식: `{ADMIN_PREFIX}/{app_id}` (예: `/v1/admin/dayoff`)
*   **STATIC 앱 유연성 확보**: `STATIC` 타입 앱이라 하더라도 하위 레코드(예: 특정 페이지)에 연결하고 싶은 경우, 인스턴스 ID가 지정되어 있다면 상세 주소 치환 로직을 타도록 예외 처리를 개선했습니다.
*   **데이터 정합성 보장**: 메뉴 정보를 페칭할 때 `db.expire_all()`을 실행하여, 최신 DB 정보가 메뉴에 실시간으로 반영되도록 신뢰도를 높였습니다.

---

## 3. 프론트엔드 UI/UX 개편 ([menu/+page.svelte](file:///home/lee/uv-code/test/svelte/src/routes/v1/admin/menu/+page.svelte))

### 🔗 통합 셀렉트 박스 기반 메뉴 관리 UI
*   **단일 선택 인터페이스**: 기존의 복잡한 이원화 구성을 하나의 세련된 셀렉트 박스로 통합하여 UX를 개선했습니다.
*   **계층적 옵션 배치**:
    *   **Level 1 (ID: 0 / 빈 값)**: 해당 앱의 **서비스 기본 화면 (기항)** (예: 휴무 신청서, 게시판 메인 등)
    *   **Level 2 (ID: -1 / 고정)**: 해당 앱의 **전용 엔진 관리 도구** (예: 승인 관리, 게시판 설정 등)
    *   **Level 3 (Real IDs)**: 게시판([board](file:///home/lee/uv-code/test/domain/v1/admin/admin_router.py#294-297))이나 페이지([page](file:///home/lee/uv-code/test/domain/page/page_router.py#74-102)) 등 상세 인스턴스/레코드 목록 (아이콘과 함께 나열)
*   **가이드 제공**: 하단에 안내 문구를 추가하여 '기본 화면'과 '관리 도구'의 차이를 명확히 인지하게끔 돕습니다.

---

## 4. 앱 메타데이터 정합성 확보 ([AppRegistry](file:///home/lee/uv-code/test/models.py#89-111))

*   **v1 체계 동기화**: [page](file:///home/lee/uv-code/test/domain/page/page_router.py#74-102) 엔진과 [dayoff](file:///home/lee/uv-code/test/domain/v1/admin/admin_router.py#340-360) 앱의 `frontend_route`에 누락되었던 `/v1/` 접두어를 추가하여 시스템 전체의 라우팅 정합성을 완벽히 맞추었습니다.

---

> [!IMPORTANT]
> **개발자 가이드**: 새로운 앱 기능을 추가할 때, `/v1/admin/[앱ID]` 경로에 관리용 페이지(admin route)만 생성하면, 메뉴 어드민에서 별도의 코드 수정 없이 즉시 해당 관리 도구를 메뉴로 등록하여 사용할 수 있습니다.
