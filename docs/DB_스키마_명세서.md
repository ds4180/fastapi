# 🗄️ 데이터베이스 스키마 명세서 (Database Schema Specification)

> **최종 업데이트**: 2026-03-11
> **DBMS**: PostgreSQL (Docker Environment)
> **Base Class**: SQLAlchemy `Base`

---

## 1. 🔑 사용자 및 인증 (Core & Auth)

### 1.1 `users` (사용자 마스터)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 고유 식별자 |
| `username` | String | Unique, Not Null | 사용자 계정 ID |
| `password` | String | Not Null | 해싱된 비밀번호 |
| `email` | String | Unique, Not Null | 이메일 주소 |
| `real_name` | String | Nullable | 실제 이름 |
| `phone` | String | Nullable | 전화번호 |

### 1.2 `user_profiles` (사용자 상세 정보)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `user_id` | Integer | PK, FK(`users.id`) | 사용자 ID (1:1 관계) |
| `rank_level` | Integer | Default: 0 | 사용자 등급 (0~4) |
| `is_active` | Boolean | Default: True | 계정 활성화 여부 |
| `employee_no`| String | Nullable | 사원 번호 |
| `joined_date` | Date | Nullable | 입사일 |
| `admin_memo` | Text | Nullable | 관리자용 메모 |

### 1.3 `user_session` (멀티 디바이스 세션 관리)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 세션 고유 ID |
| `user_id` | Integer | FK(`users.id`) | 사용자 ID |
| `session_key` | String | Unique, Index | JWT 또는 세션 키 |
| `device_category` | String | Index | Mobile, Desktop 등 |
| `status` | String | Index, Default: 'ACTIVE' | ACTIVE, LOGOUT 등 |
| `login_at` | DateTime | Index | 로그인 일시 |

---

## 2. 🚀 시스템 추상화 아키텍처 (Abstraction)

### 2.1 `app_registry` (앱 엔진 명부)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `app_id` | String | PK, Index | 앱 고유 식별자 (board, dayoff 등) |
| `name` | String | Not Null | 엔진 관리용 이름 |
| `app_type` | String | Default: 'INSTANCE' | INSTANCE, STATIC, SYSTEM |
| `frontend_route` | String | Nullable | Svelte 라우트 템플릿 |
| `main_component` | String | Nullable | Svelte 엔진 컴포넌트 명 |
| `min_read_rank` | Integer | Default: 0 | 진입 최소 등급 |
| `min_write_rank` | Integer | Default: 2 | 행위 최소 등급 |
| `config_schema` | JSONB | Default: {} | 동적 경로 치환 등 메타데이터 |

### 2.2 `menu` (지능형 사이드바 메뉴)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 메뉴 ID |
| `parent_id` | Integer | FK(`menu.id`) | 부모 메뉴 ID (Tree 구조) |
| `title` | String | Not Null | 메뉴 표시 이름 |
| `link_type` | String | Default: 'URL' | URL, APP, PAGE, DIVIDER |
| `app_id` | String | FK(`app_registry.app_id`) | 연결된 앱 엔진 ID |
| `app_instance_id` | Integer | Nullable | 앱의 특정 인스턴스 ID |
| `order` | Integer | Default: 0 | 정렬 순서 |
| `min_rank` | Integer | Default: 0 | 노출 최소 등급 (입구 컷) |

---

## 3. 🧩 서비스 및 바인딩 (Lego plugins)

### 3.1 `service_registry` (서비스 대분류)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | String | PK | 서비스 종류 ID (comment, upload 등) |
| `name` | String | Not Null | 서비스 명칭 |

### 3.2 `service_engine` (서비스 실행 엔진)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | String | PK | 엔진 ID (basic_comment_v1 등) |
| `registry_id` | String | FK(`service_registry.id`) | 서비스 종류 연결 |
| `frontend_plugin` | String | Nullable | 렌더링할 플러그인 컴포넌트 |
| `config_schema` | JSONB | Default: {} | 엔진별 필수 설정 규격 |

### 3.3 `service_binding` (앱-서비스 연결 접착제)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 바인딩 ID |
| `target_app` | String | Index | 대상 앱 ID (board 등) |
| `target_id` | Integer | Index | 대상 인스턴스 ID |
| `engine_id` | String | FK(`service_engine.id`) | 조립할 엔진 ID |
| `custom_config` | JSONB | Default: {} | 바인딩별 커스텀 설정 |
| `min_write_rank` | Integer | Nullable | 엔진별 권한 (Null 시 앱 설정 상속) |

---

## 4. 📝 게시판 시스템 (Board & Post)

### 4.1 `board_config` (게시판 인스턴스 설정)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 보드 ID |
| `slug` | String | Unique, Index | 접속 경로 (notice, free 등) |
| `name` | String | Not Null | 게시판 이름 |
| `layout_type` | String | Default: 'list' | list, gallery, blog, faq |
| `fields_def` | JSONB | Default: [] | 커스텀 폼 필드 정의 |
| `options` | JSONB | Default: {} | 댓글사용, 파일사용 등 기능 토글 |

### 4.2 `post` (게시물 데이터)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 포스트 ID |
| `board_id` | Integer | FK(`board_config.id`) | 소속 게시판 |
| `user_id` | Integer | FK(`users.id`) | 작성자 |
| `title` | String | Not Null | 제목 |
| `content` | Text | Nullable | HTML 본문 |
| `content_json` | JSONB | Not Null | TipTap JSON 데이터 |
| `extra_data` | JSONB | Default: {} | 커스텀 필드 입력 값 |
| `view_count` | Integer | Default: 0 | 조회수 |

---

## 5. 📅 기타 비즈니스 (Business Logic)

### 5.1 `dayoff` (결근/휴무 신청)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 신청 ID |
| `user_id` | Integer | FK(`users.id`) | 신청자 |
| `date` | Date | Not Null | 휴무 날짜 |
| `type` | String | Not Null | ANNUAL, SICK 등 |
| `status` | String | Default: 'REQUESTED'| REQUESTED, APPROVED, REJECTED |
| `group_id` | String | Index | 연속 휴무 그룹화 ID |

### 5.2 `alert` (시스템 공지/알림)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | 알림 ID |
| `message` | Text | Not Null | 알림 내용 |
| `level` | Integer | Default: 1 | 중요도 (1~3) |
| `style` | String | Default: 'info' | UI 스타일 |
| `route` | String | Nullable | 노출 특정 경로 |
| `is_active` | Boolean | Default: True | 활성화 여부 |

---
**문서 작성**: Gemini CLI Agent
**시스템 버전**: v1.5.1 정식 규격 반영
