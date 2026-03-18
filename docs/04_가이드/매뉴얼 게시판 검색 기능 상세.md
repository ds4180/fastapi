# Step 2: 검색 시스템 및 상태 보존(Persistence) 가이드

이 문서는 게시판 프로젝트의 검색 기능 구현과 사용자가 상세 페이지 방문 후 목록으로 돌아왔을 때 이전 검색 상태를 유지하는 아키텍처를 정리합니다.

## 1. 검색 엔진 아키텍처 (Backend)

### SQL 필터링 (FastAPI & SQLAlchemy)
- **위치**: `domain/question/question_crud.py`
- **구현 방식**:
    - `keyword` 파라미터가 존재할 경우, 제목(`subject`), 내용(`content`), 작성자명(`username`)을 대상으로 `OR` 조건 검색을 수행합니다.
    - `ilike` 연산자를 사용하여 대소문자 구분 없이 부분 일치 검색을 지원합니다.
    - `distinct()`를 사용하여 중복 결과를 방지합니다.

```python
if keyword:
    search = f"%%{keyword}%%"
    _question_list = _question_list.filter(
        or_(
            Question.subject.ilike(search),
            Question.content.ilike(search),
            User.username.ilike(search)
        )
    ).distinct()
```

## 2. 상태 보존 시스템 (Frontend)

사용자 경험(UX) 극대화를 위해 검색 조건과 페이지 위치를 브라우저 세션에 보관합니다.

### 🧠 전역 상태 관리 (Svelte Store)
- **위치**: `src/lib/store.js`
- **역할**: `lastViewedPage`(숫자형), `keyword`(문자열형) 두 개의 스토어를 운영합니다.
- **Persistence**: `sessionStorage`와 연동되어 페이지를 새로고침하거나 탭을 닫기 전까지 상태가 유지됩니다.

### 🔄 상태 동기화 프로세스
1. **기록**: `question_list` 페이지가 로드될 때마다 URL의 `page`와 `keyword` 정보를 전역 스토어에 즉시 업데이트합니다.
2. **보존**: 사용자가 목록에서 검색하거나 페이지를 넘길 때마다 스토어 값이 자동으로 세션 스토리지에 저장됩니다.
3. **복원**: `question_list/[question_id]` 페이지(상세)에서 '목록으로' 버튼을 누를 때, 스토어에 저장된 값을 읽어와 이전 URL을 동적으로 복원합니다.

```svelte
<!-- 상세 페이지의 목록 복원 버튼 코드 -->
<a href={`/question_list?page=${$lastViewedPage}&keyword=${$keyword}`}> 목록으로 </a>
```

## 3. 주요 UX 개선 사항
- **연속성 보장**: 상세 페이지 확인 후 뒤로가기가 아닌 '목록으로' 버튼을 눌러도 보던 위치 그대로 복귀합니다.
- **불필요한 요청 감소**: 사용자가 이전 검색 결과를 찾기 위해 재검색할 필요가 없어 서버 부하를 줄이고 사용자 편의성을 높였습니다.

---

## 4. 향후 확장 가능성 (매운맛 예고)
- **다중 키워드 검색**: 공백(Space)으로 구분된 여러 단어를 모두 포함하는 결과 필터링.
- **검색어 하이라이트**: 결과 목록에서 검색어 부분을 시각적으로 강조.
- **상세 필터**: 제목, 내용, 저자 등 검색 대상을 선택할 수 있는 옵션 제공.
