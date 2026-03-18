---
제목: 데이터베이스 설계 및 명명 규칙 (v1.0)
날짜: 2026-03-09
작성자: Antigravity (AI)
카테고리: 01_표준정의
태그: #Database #SQLAlchemy #Naming-Convention #PostgreSQL
상태: Completed
---

# 🗄️ 데이터베이스 설계 및 명명 규칙 (DB Standard)

> 이 문서는 프로젝트의 데이터 일관성과 관리 용이성을 위해 필드명, 테이블 설계 및 마이그레이션에 대한 표준을 정의합니다.

---

## 1. 배경 및 목적 (Background & Motivation)
서로 다른 개발 시기에 만들어진 테이블들이 `create_date`, `created_at`, `registered_date` 등 각기 다른 필드명을 사용하는 문제를 해결하고, NoSQL과 RDBMS의 장점을 결합한 하이브리드 설계를 지향합니다.

## 2. 명명 규칙 (Naming Conventions)

### 2.1 테이블명 (Table Names)
- **규칙**: 소문자 및 언더바(`snake_case`)를 사용하며, 단수형을 권장합니다.
- **예시**: `user`, `board_config`, `post_read`

### 2.2 필드명 (Field Names)
- **ID**: 기본키는 `id` (Integer)를 사용합니다.
- **시간 필드 (Timestamp)**: 
    - 생성 시각: `create_date` (DateTime)
    - 수정 시각: `modify_date` (DateTime)
    - 삭제 시각: `delete_date` (DateTime)
    - *이유: 기존 레거시(`Question`, `Answer`)의 `create_date`와 통일성을 유지하여 쿼리 복잡도를 낮춥니다.*
- **상태 필드**: `status`, `is_active`, `is_deleted` (Boolean)를 사용합니다.

### 2.3 관계 설정 (Relationships)
- **ForeignKey**: `소속테이블_id` 형식을 사용합니다. (예: `user_id`, `board_id`)
- **Many-to-Many**: `테이블A_테이블B` 형식의 매핑 테이블을 사용합니다. (`[표준]리소스_보안` 참조)

## 3. 하이브리드 설계 (JSONB 활용)
- 고정된 정형 데이터는 전용 컬럼으로 분리합니다.
- 확장이 잦거나 보드마다 성격이 다른 유동 데이터는 `extra_data` (JSONB) 컬럼에 저장합니다.

## 4. 성과 및 학습 포인트 (Outcome & Learning)
- **일관성 확보**: 모든 모델이 동일한 시간 필드(`create_date`)를 가짐으로써, 전역적인 정렬 및 통계 처리가 쉬워졌습니다.
- **학습 포인트**: **"일관된 명명 규칙(Naming Convention) 하나만으로도 수십 시간의 디버깅 비용을 줄일 수 있음"**을 실감했습니다.

---

### 📜 변경 이력 (Change Log)
- **2026-03-09**: [Antigravity] DB 명명 규칙 표준 최초 정의.
