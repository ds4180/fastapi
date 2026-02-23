# 중요 문서 변경 이력 관리 표준

이 문서는 프로젝트 내 중요 데이터(문서, 설정 등)의 변경 사항을 추적하고 조회하기 위한 표준 데이터베이스 스키마와 구현 워크플로우를 정의합니다.

## 1. 핵심 원칙 (Core Principles)

모든 변경 이력 관리는 아래 3가지 핵심 원칙을 따릅니다.

1.  **Diff/Patch 방식 채택**
    - **원칙**: 변경 시, 문서 전체를 복사하여 저장하는 대신 **이전 버전과의 차이점(Diff)만**을 구조화된 데이터(JSON)로 저장합니다.
    - **이유**: 저장 공간의 효율성을 극대화하고, 변경된 부분을 명확하게 식별하여 사용자에게 제시하기 위함입니다.

2.  **논리적 삭제 (Soft Delete)**
    - **원칙**: 사용자가 문서를 '삭제'할 경우, 데이터베이스에서 물리적으로 제거(`DELETE`)하지 않고 `is_deleted` 플래그를 `True`로 설정합니다.
    - **이유**: 삭제된 문서와 그 이력을 포함한 모든 기록을 보존하여, 감사(Audit) 추적 및 데이터 복구 가능성을 확보하기 위함입니다.

3.  **버전 관리 (Versioning)**
    - **원칙**: 문서가 변경될 때마다 정수형 `version` 번호를 1씩 증가시킵니다.
    - **이유**: "사용자가 마지막으로 확인한 버전 이후의 변경사항만 보여주기"와 같은 기능을 구현하는 핵심적인 역할을 하며, 변경 순서를 명확하게 보장합니다.

---

## 2. 데이터베이스 스키마 (Database Schema)

### `documents` 테이블 (최신 상태)

문서의 현재 상태를 저장합니다.

| 컬럼명 | DB 타입 (SQLAlchemy) | Python 타입 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | `int` | Primary Key |
| `title` | `String(255)` | `str` | 문서 제목 |
| `content` | `Text` | `str` | 문서 본문 |
| **`version`** | **`Integer`** | **`int`** | **문서 버전. 수정 시 1씩 증가.** |
| **`is_deleted`** | **`Boolean`** | **`bool`** | **삭제 여부 플래그.** |
| `deleted_at` | `DateTime` | `datetime.datetime` | 삭제 시각 |
| `created_at` | `DateTime` | `datetime.datetime` | 생성 시각 |
| `updated_at` | `DateTime` | `datetime.datetime` | 마지막 수정 시각 |

### `document_history` 테이블 (변경 이력)

문서의 모든 변경 이력을 Diff 형태로 누적 저장합니다.

| 컬럼명 | DB 타입 (SQLAlchemy) | Python 타입 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | `int` | Primary Key |
| `document_id` | `Integer` | `int` | 원본 문서의 ID (FK) |
| **`version`** | **`Integer`** | **`int`** | **이 변경으로 적용된 버전 번호.** |
| `change_type` | `Enum` | `str` | 변경 유형 (`CREATED`, `UPDATED`, `DELETED`) |
| **`changes`** | **`JSONB`** | **`list`** | **핵심. 변경사항 Diff 객체(JSON) 저장.** |
| `summary` | `String(500)` | `str` | 변경 요약 메시지 (예: "제목, 내용 필드 수정") |
| `changed_by_user_id`| `Integer` | `int` | 변경을 수행한 사용자 ID |
| `changed_at` | `DateTime` | `datetime.datetime`| 변경 발생 시각 |


> [!NOTE]
> **ORM 관계 설정**
> SQLAlchemy 모델에서는 `relationship`과 `back_populates`를 사용하여 `Document`와 `DocumentHistory` 객체 간의 양방향 참조를 설정합니다.
> 단, 원본 문서 삭제 시 이력이 함께 삭제되는 것을 방지하기 위해 `cascade` 옵션은 절대 사용하지 않습니다.

---

## 3. 구현 워크플로우

### 문서 수정 시 (On Document Update)

1.  데이터베이스 트랜잭션을 시작합니다.
2.  수정할 원본 문서를 DB에서 조회합니다.
3.  원본 문서와 사용자가 제출한 수정 데이터를 비교하여 **Diff(Patch) 객체를 생성**합니다. (아래 `jsonpatch` 라이브러리 참고)
4.  `DocumentHistory` 테이블에 새로운 레코드를 생성합니다. 이 레코드에는 `document_id`, 새로운 `version` 번호, `change_type`('UPDATED'), 그리고 생성된 **Diff 객체**를 포함합니다.
5.  `Document` 테이블의 원본 문서를 업데이트하고, `version` 번호를 1 증가시킵니다.
6.  트랜잭션을 커밋합니다.

### 변경 이력 조회 시 (On Viewing History)

1.  특정 `document_id`에 해당하는 `document_history` 목록을 `changed_at` 기준으로 정렬하여 조회합니다.
2.  프론트엔드는 히스토리 레코드의 `changes` (Diff 데이터)를 해석하여 사용자에게 변경 전/후 내용을 시각적으로 명확하게 비교하여 보여줍니다. (예: GitHub의 Diff 뷰)

---

## 4. 권장 라이브러리: `jsonpatch`

두 JSON(딕셔너리) 객체 간의 Diff 생성 및 적용을 위해 `jsonpatch` 라이브러리 사용을 표준으로 합니다.

- **설치**: `pip install jsonpatch`

- **기본 사용법**:
    ```python
    import jsonpatch

    # 원본 문서와 수정된 문서
    original_doc = {'title': '원본 제목', 'tags': ['A', 'B']}
    modified_doc = {'title': '수정된 제목', 'tags': ['A', 'C'], 'status': 'done'}

    # Diff (Patch) 생성
    patch = jsonpatch.make_patch(original_doc, modified_doc)
    diff_data = patch.patch 
    # diff_data는 [{'op': 'replace', 'path': '/title', ...}, ...] 형태의 리스트가 됩니다.

    # 이 diff_data를 document_history 테이블의 'changes' 컬럼에 저장합니다.
    ```
