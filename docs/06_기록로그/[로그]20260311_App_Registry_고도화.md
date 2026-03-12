# [로그] 2026-03-11 App Registry 시스템 통합 및 고도화 (v1.5)

## 1. 개요
기존에 산재해 있던 App Registry 관련 API와 UI를 하나의 표준 경로(`/v1/admin/app`)로 통합하고, 하드코딩이 제거된 데이터 기반 동적 아키텍처로 업그레이드함.

## 2. 주요 변경 사항

### 2.1 백엔드 (FastAPI)
- **API 통합**: 구형 `/app` 엔드포인트를 폐기하고, 고도화된 `/v1/admin/apps` (v1.5)로 단일화.
- **동적 URL 해석기**: `resolve_menu_url` 함수에서 `if app_id == "board"` 분기문을 제거. 이제 `AppRegistry`의 메타데이터를 사용하여 동적으로 모델을 조회하고 경로를 생성함.
- **보안 강화**: `min_read_rank`, `min_write_rank` 이원화 및 `admin_ids`를 통한 관리 권한 위임 로직 반영.
- **정합성 수정**: `admin_router.py` 내의 모든 스키마 참조를 `admin_schema.` 네임스페이스 방식으로 교정하여 `NameError` 완전 해결.

### 2.2 프론트엔드 (Svelte 5)
- **경로 단일화**: 임시 경로(`/app-manage`)를 삭제하고 기존 표준 경로인 `/v1/admin/app`으로 UI 통합.
- **로직 최적화**: `Form Actions` (+page.server.js) 방식을 폐기하고, 전역 통신 엔진인 `admin.api.js`를 사용한 실시간 Fetch 방식으로 전환.
- **UI 업그레이드**: Svelte 5 룬($state, $effect)을 활용하여 반응형 관리 인터페이스 구축.

## 3. 시행착오 및 해결
- **빌드 권한 이슈**: Docker가 생성한 데이터 폴더 권한 문제로 빌드 실패 → `.dockerignore`에 제외 항목 추가 및 환경 정리로 해결.
- **코드 중복 및 충돌**: 신규 기능 추가 시 기존 기능을 덮어쓰는 실수 발생 → 파일 전수 조사 및 정밀 리팩토링을 통해 단일 표준 구조로 복구 및 통합.

## 4. 향후 과제
- `AppRegistry`에 등록된 `config_schema`를 기반으로, 각 앱 인스턴스 설정 시 동적 폼(Dynamic Form) 생성 기능 추가 검토.
- 차량 관리 등 신규 앱 추가 시 메타데이터 등록만으로 정상 작동하는지 최종 실무 테스트.

---
**작성자**: Gemini CLI Agent (with User)
**상태**: 완료 (Completed)
