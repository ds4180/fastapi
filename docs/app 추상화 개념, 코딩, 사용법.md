# 🚀 시스템 App 기반 추상화 아키텍처 가이드 (v1.0)

이 문서는 게시판을 넘어, 시스템의 모든 기능을 독립된 'App'으로 관리하고 실행하기 위해 설계된 **메타데이터 기반 추상화 시스템**의 개념과 구현, 그리고 사용법을 상세히 기술합니다.

---

## 1. 🌟 추상화의 핵심 개념 (The Concept)

### 왜 추상화인가?
기존 방식은 새로운 기능을 추가할 때마다 개발자가 직접 라우트(Route)를 만들고 페이지를 코딩해야 했습니다. 하지만 본 프로젝트의 추상화 시스템은 **"기능(Engine)"**과 **"설정(Metadata)"**을 분리합니다.

### 무엇이 달라졌는가? (The Difference)
- **과거**: 게시판 하나 추가 = 폴더 복사 + 코드 수정 + 빌드 + 수동 메뉴 등록
- **현재**: 게시판 하나 추가 = 관리자 페이지에서 **클릭 한 번으로 앱 엔진 호출**
- **주소 체계**: 은행 사이트와 유사한 `/app/[app_id]/[instance_id]` 구조를 사용하여 통일성과 확장성을 확보했습니다.

---

## 2. 🏗️ 아키텍처 구조 (Architecture)

시스템은 크게 세 단계의 레이어로 작동합니다.

### Layer 1: 데이터베이스 (AppRegistry & Menu)
- **`AppRegistry`**: "이런 엔진(App)이 설치되어 있다"는 장부입니다. (예: `board`, `calendar`)
- **`Menu`**: 특정 앱의 특정 인스턴스(예: 공지사항 게시판)를 가리킵니다. 주소를 직접 저장하지 않고 앱의 ID만 가리키는 지능형 구조입니다.

### Layer 2: 서버 및 통신 (FastAPI & Hooks)
- **지능형 메뉴 로직**: 백엔드가 메뉴 정보를 줄 때, 앱의 설정값(`frontend_route`)을 읽어와서 `/app/board/notice` 같은 최종 URL을 실시간으로 조립합니다.
- **권한 해제**: 앱 메타데이터 조회 API를 전체 공개하여, 로그인 여부와 관계없이 시스템 구조를 파악할 수 있게 합니다.

### Layer 3: 프론트엔드 (Engines & Launcher)
- **컴포넌트 지도 (`lib/index.js`)**: 모든 엔진 컴포넌트들을 이름표를 붙여 관리합니다.
- **범용 실행기 (`routes/app/...`)**: 주소창의 `app_id`를 보고 지도에서 컴포넌트를 찾아 화면에 **"쏙 끼워 넣는(Dynamic Injection)"** 역할을 합니다.

---

## 3. 📂 파일 변경 및 생성 이력 (Development Log)

### [생성] svelte/src/lib/components/BoardEngine.svelte
- **역할**: 모든 게시판의 UI를 책임지는 '표준 그릇'입니다.
- **특징**: `slug`를 주입받아 스스로 데이터를 로딩하며, 목록/상세/쓰기 모드를 내부적으로 전환합니다.

### [생성] svelte/src/routes/app/[app_id]/[...slug]/
- **역할**: 추상화된 앱들이 실행되는 범용 무대(Viewport)입니다.
- **로직**: `app_id`로 DB를 조회해 어떤 컴포넌트를 띄울지 결정합니다.

### [수정] models.py & migrations
- **`AppRegistry` 테이블 신설**: `frontend_route`, `main_component`, `api_module` 등 추상화 메타데이터를 담는 주머니를 만들었습니다.
- **`Menu` 테이블 확장**: `app_id`, `app_instance_id` 필드를 추가하여 앱 엔진과 직접 연결했습니다.

### [수정] domain/v1/admin/admin_router.py
- **`resolve_menu_url` 추가**: 메뉴 타입이 `APP`인 경우 자동으로 주소를 조립하는 핵심 엔진을 탑재했습니다.

---

## 4. 🛠️ 사용 방법 (How to use)

### 새로운 App 엔진 등록하기 (개발자용)
1. `lib/components/`에 새로운 엔진(예: `CalendarEngine.svelte`)을 만듭니다.
2. `lib/index.js`에 해당 컴포넌트를 등록합니다.
3. 관리자 페이지(`v1/admin/app`)에서 새 앱을 등록합니다.
   - **main_component**: `CalendarEngine` (이름 정확히 일치)
   - **frontend_route**: `/app/calendar`

### 메뉴에 앱 연결하기 (관리자용)
1. 메뉴 관리(`v1/admin/menu`)로 이동합니다.
2. `메뉴 성격`을 **'🚀 시스템 App 연결'**로 선택합니다.
3. 원하는 앱(예: 게시판 엔진)과 세부 인스턴스(예: 공지사항)를 선택하고 저장합니다.
4. 이제 시스템이 주소를 자동으로 계산하여 연결해 줍니다.

---

## 5. ⚠️ 주의사항 및 시행착오 (Lessons Learned)

1. **컴포넌트 이름 매칭**: `AppRegistry`에 적는 `main_component` 이름은 `lib/index.js`에서 내보내는(export) 이름과 대소문자까지 완벽히 같아야 합니다.
2. **함수명 불일치 주의**: 엔진 제작 시 `api_module`(`board.api.js`)에 정의된 실제 함수명을 사용해야 합니다. (예: `getPostList`가 아닌 `getBoardPosts`)
3. **Frontend Route 규칙**: 앱 등록 시 `frontend_route`에 `/app/board/[slug]`와 같이 전체 경로 템플릿을 적어주어야 지능형 메뉴가 작동합니다.

---
**최종 업데이트**: 2026-03-03
**버전**: v1.0 (App Abstraction Milestone)
**좌우명**: "코딩은 한 번만, 서비스는 무한히."
