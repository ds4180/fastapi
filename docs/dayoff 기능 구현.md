## 1. DayOff 기능 구현 계획

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
