# DayOff 기능 구현 계획 및 프로젝트 표준 정의

이 문서는 `DayOff` 기능 구현 계획뿐만 아니라, **프로젝트 전체에서 따를 날짜와 시간 처리의 표준**을 정의합니다.

## 1. 프로젝트 날짜/시간 표준 (Project Standards)

프로젝트 전반의 일관성을 위해 모든 날짜/시간 데이터는 아래 규칙을 따릅니다.
특히 **시각(Point in Time)**과 **시간의 양(Duration)**을 명확히 구분합니다.

| 구분 | 의미 | DB 타입 (SQLAlchemy) | Python 타입 | 단위/포맷 | 예시 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **날짜 (Date)** | 특정 날짜 (시각 없음) | **`Date`** (String 아님) | `datetime.date` | - | `2024-02-14` |
| **시각 (Time)** | 하루 중 특정 시점 | `Time` | `datetime.time` | - | `14:30:00` |
| **일시 (DateTime)** | 날짜 + 시각 | `DateTime` | `datetime.datetime` | - | `2024-02-14 14:30` |
| **시간의 양 (Duration)** | **절대적 시간 (근무시간, 휴게시간)** | **`Integer`** | **`int`** | **분 (Minute)** | `90` (= 1시간 30분) |

### 기술적 구현 전략

#### 1. 시간의 양 (Duration) - **절대적 시간 개념**
- **저장**: 모든 소요 시간, 근무 시간, 휴게 시간은 **분(Minute)** 단위의 **정수(Integer)**로 저장합니다.
- **계산**: 정수 사칙연산을 사용하여 오차 없는 합산 및 차감 계산을 수행합니다. (예: `480분 - 60분 = 420분`)
- **표시**: 화면에 보여줄 때만 `n시간 m분` 형태로 변환합니다.

#### 2. 날짜 및 시각 (Point in Time) - 타임존 전략
- **환경 설정**: 모든 서버 컨테이너(FastAPI, Svelte)에 **`TZ=Asia/Seoul`** 환경 변수를 설정하여 시스템 타임존을 한국(KST)으로 고정합니다.
- **백엔드/DB**: 시스템 타임존이 KST이므로, 별도의 타임존 계산(KST+9 등) 없이 `datetime.now()` 같은 기본 함수를 사용하여 한국 시각을 저장하고 관리합니다. (DB 타입은 `DateTime` 사용)
- **프론트엔드**: 서버로부터 받은 시각 문자열(KST)을 타임존 변환 없이 그대로 사용하며, `utils.js` 등을 통해 간단한 포맷팅만 수행합니다. (복잡한 모멘트/타임존 라이브러리 배제)

---

## 2. DayOff 기능 구현 계획

### 데이터베이스 및 백엔드

#### [MODIFY] [models.py](file:///home/lee/uv-code/test/models.py)

> [!CAUTION]
> **DB 모델링 최종 결정 사항 (Enum 처리)**
> - **DB 컬럼 타입**: `String` (VARCHAR) 사용.
> - **이유**: 마이그레이션 유연성 확보.
> - **검증**: 애플리케이션 레벨(Pydantic)에서 엄격하게 통제.

- **`DayOff` 모델 추가** (완료됨)
    - `date`: `Date`
    - `user_id`: Integer
    - `type`: `String`
    - `status`: `String`
    - `category`: `String`
    - `memo`: `String`
    - `create_date`: `DateTime`
    - **UniqueConstraint**: `(user_id, date)`

#### [NEW] [domain/dayoff/dayoff_schema.py](file:///home/lee/uv-code/test/domain/dayoff/dayoff_schema.py) (완료됨)
- **Enum 정의**: `DayOffType`, `DayOffStatus`
- `DayOffCreate`, `DayOffResponse`

#### [NEW] [domain/dayoff/dayoff_crud.py](file:///home/lee/uv-code/test/domain/dayoff/dayoff_crud.py) (완료됨)
- `create_dayoff`: `type`을 인자로 받아 저장.

### 프론트엔드
#### [MODIFY] [svelte/src/routes/day_off/+page.svelte](file:///home/lee/uv-code/test/svelte/src/routes/day_off/+page.svelte)
> [!IMPORTANT]
> **UI 통합 결정**
> 별도의 목록 페이지(`list/+page.svelte`)를 만들지 않고, **달력 페이지 하단**에 목록과 취소 기능을 통합합니다.
> 한 화면에서 "선택 -> 저장 -> 확인 -> 취소" 흐름이 모두 가능하도록 구성합니다.

- **상단: 달력 및 입력 폼**:
    - 달력: 날짜 선택
    - 입력폼: 휴무 유형(라디오), 메모(텍스트)
    - 저장 버튼: 선택된 날짜들을 서버로 전송
- **하단: 내 휴무일 목록**:
    - 백엔드에서 `GET /api/dayoff/list` 호출하여 데이터 로드
    - 테이블 형태로 표시: `날짜`, `유형`, `상태`, `메모`, `등록일시`, `[취소]` 버튼
    - **취소 버튼**: 클릭 시 `DELETE /api/dayoff/delete/{id}` 호출 후 목록 갱신

## 검증 계획
### 수동 검증
1.  **유형 선택 저장**: "병가"로 선택하여 저장 후, 리스트에 "병가"로 나오는지 확인.
2.  **상태 확인**: 저장 직후 상태가 "신청(REQUESTED)"인지 확인.
3.  **중복 방지**: 같은 날짜 중복 등록 시도 시 에러(또는 무시) 확인.
4.  **취소 기능**: 목록에서 취소 버튼 클릭 시 해당 항목이 사라지는지 확인.
