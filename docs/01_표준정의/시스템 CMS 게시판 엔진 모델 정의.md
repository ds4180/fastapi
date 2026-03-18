# 📋 시스템: CMS 게시판 엔진 모델 정의

> 이 문서는 단순한 게시판을 넘어, **설정 기반의 무한 확장형 CMS(Content Management System)** 엔진의 구조와 설계 철학을 정의합니다.

> 이 문서는 단순한 게시판 구현을 넘어, **설정 기반의 유연한 CMS(Content Management System)**로 확장하기 위한 게시판 모델의 구조와 철학을 정의합니다.

---

## 1. 배경 및 목적 (Background & Motivation)
초기 프로젝트는 단순한 질문-답변(Q&A) 위주의 게시판으로 시작되었습니다. 하지만 서비스가 확장됨에 따라 공지사항, 자유게시판, 갤러리, 업무 보고 등 다양한 형태의 게시판이 필요하게 되었습니다. 

본 표준의 목적은 **기능을 추가할 때마다 코드를 새로 짜는 것이 아니라, 설정을 통해 게시판의 성격을 결정하는 '확장 기능(Extended Board)'** 모델을 확립하는 것입니다.

## 2. 기존 방식의 문제점 (Analysis of Current State)
- **코드 중복**: 새로운 게시판이 필요할 때마다 유사한 CRUD 코드가 반복 생성됨.
- **경직된 스키마**: `Question` 모델처럼 고정된 필드만 사용할 경우, 가격 정보나 마감일 등 특수한 데이터를 담기 어려움.
- **관리 비효율**: 게시판마다 다른 권한 로직이나 UI 레이아웃을 하드코딩으로 관리함에 따른 유지보수 비용 증대.

## 3. 해결 방안 및 핵심 로직 (Solution & Key Changes)

### 3.1 설정 기반의 CMS 모델 (`BoardConfig`)
게시판의 모든 특성을 데이터베이스 테이블(`BoardConfig`)로 격리하여 관리합니다.
- **레이아웃 타입**: `list`, `gallery`, `split_view` 등 UI를 설정으로 결정.
- **권한 이원화**: `읽기`는 메뉴의 `min_rank`에 위임하고, `쓰기`는 `BoardConfig`의 `min_write_rank`로 제어합니다. (권한 이원화 원칙 준수)
- **기능 스위치**: 댓글 사용 여부, 파일 업로드 허용 여부 등을 `options` 필드(JSONB)로 On/Off.

### 3.2 통합 콘텐츠 모델 (`Post`)
모든 게시물은 단일 `Post` 테이블에 저장되되, 게시판별 특수 데이터는 `extra_data` (JSONB) 필드에 담아 확장성을 확보합니다.

## 4. 상세 구현 내용 (Implementation Details)

### 4.1 SQL 스키마 (Power of JSONB)
```python
class BoardConfig(Base):
    __tablename__ = "board_config"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, index=True) # URL 식별자
    name = Column(String, nullable=False)
    layout_type = Column(String, default="list")
    
    # 기능 및 권한 설정 (핵심)
    fields_def = Column(JSONB, default=list)  # 동적 필드 정의
    # 권한 설정 (이원화 모델)
    min_write_rank = Column(Integer, default=2) # 쓰기 최소 권한 (읽기는 Menu 위임)
    options = Column(JSONB, default=dict)       # comment, upload 등 기능 On/Off
```

### 4.2 기본형 vs 확장형 모델 분류
- **기본형 (Standard)**: 최소한의 CRUD와 파일 업로드를 포함하는 독립적 엔진.
- **확장형 (Extended)**: TipTap 에디터, 다중 카테고리, 실시간 알림, 커스텀 필드가 포함된 관리자형 엔진.

## 5. 성과 및 학습 포인트 (Outcome & Learning)
- **유연성 극대화**: 이제 새로운 게시판이 필요할 때 DB 레코드 하나만 추가하면 즉시 서비스가 가능해졌습니다.
- **Legacy 보호**: 기존 `Question`, `Answer` 모델을 건드리지 않고 `v1` 경로로 확장하여 안정성을 유지했습니다.
- **학습 포인트**: 데이터베이스의 **JSONB** 필드를 전략적으로 활용하면 RDBMS에서도 NoSQL과 같은 유연한 스키마 설계가 가능하다는 것을 실전에서 검증했습니다.

---

### 📜 변경 이력 (Change Log)
- **2026-03-02**: 게시판 모델 기본 정의서 작성.
- **2026-03-09**: [Antigravity] 문서 작성 표준(배경/문제/해결/학습)에 맞춰 내용 고도화 및 CMS 관점 추가.
