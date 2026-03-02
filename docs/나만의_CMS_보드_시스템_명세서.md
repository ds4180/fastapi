# 📄 나만의 CMS 보드 시스템 아키텍처 상세 명세서
(Custom CMS Board System Architecture Specification)

## 1. 개요 및 설계 철학 (Overview & Philosophy)

본 시스템은 고정된 형태의 게시판을 탈피하여, **설정(Configuration)** 기반으로 동작하는 **범용 CMS(Content Management System)**로의 전환을 목표로 한다.

- **Legacy & New Coexistence**: 기존 기능(v0)은 100% 보존하며 작동 상태를 유지한다. 모든 신규 개발은 `v1` 명칭을 사용하여 완전히 격리된 환경에서 진행한다.
- **Everything is Content**: 모든 페이지, 공지, 업무 보고, 투표 등은 하나의 `Post` 모델로 통합 관리된다.
- **Modular Plugin System**: 댓글, 파일 업로드, 실시간 알림 등은 `BoardConfig` 설정에 따라 탈부착되는 모듈로 취급한다.

---

## 2. 경로 및 네이밍 규칙 (Path & Naming Conventions) - [필독]

중복 경로 방지 및 레거시 보호를 위한 엄격한 규칙을 적용한다.

### 2.1 Backend (FastAPI)
- **API Prefix**: 모든 신규 CMS 라우터는 `prefix="/v1"`을 사용한다.
- **실제 호출 주소**: `도메인/api/v1/...` (Nginx의 `/api/` 프록시 설정을 준수하여 `/api/api/` 중복 방지)
- **폴더 구조**: `domain/v1/` 폴더 내에 `board`, `post`, `admin` 등 기능별 분리.

### 2.2 Frontend (Svelte)
- **Route Path**: 모든 신규 CMS 화면은 `svelte/src/routes/v1/...` 폴더 내에 생성한다.
- **접속 주소**: `도메인/v1/...` (기존 루트 및 게시판 주소와 충돌 방지)
- **컴포넌트**: 신규 CMS 전용 컴포넌트는 `svelte/src/lib/components/v1/`에 위치한다.

### 2.3 Legacy Handling
- 기존 파일은 절대 삭제하거나 이동하지 않는다.
- 향후 기존 위치의 파일을 교체해야 할 경우에만, 기존 파일명을 `page_v0.svelte` 등으로 변경하여 백업한다.

---

## 3. 데이터베이스 설계 (Database Schema)

### 3.1 게시판 설정 테이블 (`BoardConfig`)
| 필드명 | 타입 | 설명 | 비고 |
| :--- | :--- | :--- | :--- |
| **slug** | String | URL 식별자 (Unique) | 예: `notice`, `market` |
| **layout_type** | String | 화면 디자인 타입 | `list`, `gallery`, `split_view`, `landing` |
| **fields_def** | **JSONB** | **동적 필드 정의** | 커스텀 입력 항목 정의 |
| **options** | **JSONB** | **기능 스위치** | `comment`, `upload`, `push`, `ws` ON/OFF |

### 3.2 통합 콘텐츠 테이블 (`Post`)
| 필드명 | 타입 | 설명 | 비고 |
| :--- | :--- | :--- | :--- |
| **board_id** | Integer | 소속 게시판 (FK) | `BoardConfig` 참조 |
| **content_json**| **JSONB** | **TipTap 본문** | **JSON Node Tree** 구조 |
| **extra_data** | **JSONB** | **보드별 커스텀 데이터**| 가격, 진행률 등 자유로운 데이터 |

### 3.3 관계형 모델 (M2M)
- **PostRead (클래스형)**: 유저별 읽음 이력, 횟수, 기기(MOBILE/WORKSPACE) 정보 기록.
- **PostTag (테이블형)**: 단순 분류용 #태그 연결 정보.

---

## 4. 핵심 기술 가이드라인 (Technical Guidelines)

1. **에디터 (TipTap)**: 본문은 무조건 JSON 형식으로 저장하며, 이미지 업로드 시 기존 `fileupload_service`를 호출하여 `uploads/` 폴더와 `delete_` 정책을 그대로 계승한다.
2. **메뉴 (Menu & Iconify)**: 무제한 계층 트리 구조를 지원하며, 아이콘은 **Iconify** 표준 문자열(`mdi:home`)로 관리한다.
3. **권한 (RBAC)**: 유저의 `role`/`group`과 `BoardConfig`의 `perm_read`/`perm_write` 설정을 런타임에 대조한다.
4. **미디어 관리 (GC)**: 기존 파이썬 크론 스크립트를 고도화하여 DB와 링크가 끊긴 유령 파일(Orphaned)을 물리적으로 삭제한다.

---

## 5. 실행 지침 (Execution Principles)

1. **기존 기능 유지**: 개발 중에도 기존 `/api/question` 등 모든 기능은 정상 동작해야 한다.
2. **명세 우선**: 모든 코딩은 본 명세서의 정의를 최우선으로 따른다.
3. **DB 안정성**: `models.py` 수정 시 기존 `Question`, `Answer` 클래스는 절대 건드리지 않고 아래에 신규 모델을 추가한다.
