# ✅ TODO LIST

- [ ] **각종 로그 파일들의 설정**
  - [ ] FastAPI 로그 회전(Log Rotation) 및 보관 주기 설정 (7일/30일)
  - [ ] Docker 컨테이너 로그 크기 제한 설정 (`max-size=10m`)
  - [ ] 에러 발생 시 외부 Webhook(Discord/Slack 등) 알림 연동
  - [ ] 서비스별(Nginx, DB, App) 로그 경로 표준화 및 접근 권한 관리
  
- [ ] **PWA 관련 기능 추가**
  - [ ] `manifest.json` 아이콘 세트 보강 및 스플래시 화면 최적화
  - [ ] 서비스 워커(Service Worker)를 활용한 정적 자원 오프라인 캐싱
  - [ ] 앱 설치 유도 프론프트(Install Prompt) 커스텀 UI 구현
  - [ ] 푸시 알림(Web Push) 백그라운드 수신 및 클릭 이벤트 처리

- [ ] **Docker RAM 제한**
  - [ ] `docker-compose.yml` 내 각 서비스별 `mem_limit` 및 `cpus` 할당량 설정
  - [ ] 컨테이너별 메모리 사용량 실시간 모니터링 스크립트 도입
  - [ ] 메모리 부족(OOM) 발생 시 자동 재시작 및 경고 로깅 정책 수립

- [ ] **긴급 복구 script**
  - [ ] 데이터베이스 전체 백업 및 1-Click 복구 스크립트 (`scripts/recovery_db.sh`)
  - [ ] 컨테이너 완전 삭제 후 클린 빌드 자동화 스크립트
  - [ ] 네트워크 장애 시 브리지 네트워크 재생성 및 컨테이너 재조인 로직

- [ ] **차량 관리 앱 생성**
  - [ ] 차량 관리 통합 대시보드 앱 구현 (`STATIC` 방식)
  - [ ] 개별 차량을 위한 상세 뷰 플러그인/서비스 연동 구성
  - [ ] 직원별/기사별 개인 대시보드 앱 구현 (`INSTANCE` 방식, 강력한 권한 제어)
  - [ ] 그룹 관리 앱 구현 (동적/정적 그룹 분류 및 Redis 연동 공지 기능)
  - [ ] **Data-Driven 동적 검색 엔진 구현** (JSONB + `getattr`를 활용한 No-Code 수준의 필터 생성 및 프론트 통신)

- [ ] **MinIO 구현**
  - [ ] Docker Compose에 MinIO 서비스 추가 (포트 9000/9001)
  - [ ] `.env`에 MinIO 인증 정보(`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`) 설정
  - [ ] FastAPI에 `boto3` 기반 MinIO 클라이언트 모듈 작성 (`minio_client.py`)
  - [ ] 버킷 자동 생성 로직 구현 (앱 시작 시)
  - [ ] 파일 업로드 / 다운로드 API 엔드포인트 작성
  - [ ] Presigned URL 발급 API 구현 (프론트 직접 업로드용)
  - [ ] Svelte 프론트엔드 파일 업로드 UI 연동
  - [ ] 기존 `domain/fileupload` 도메인 MinIO로 전환
  - [ ] MinIO 가이드 문서 작성 (`04_가이드/[가이드]MinIO_파일_스토리지`)
