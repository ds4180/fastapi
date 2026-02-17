# 제1장: Hello FastAPI! 🚀
> **학습 목표:** FastAPI를 설치하고, 첫 번째 서버를 실행하여 "Hello World"를 확인합니다.

## 📌 이번 장에서 다루는 커밋
*   **Hash:** `7ea3960`
*   **Message:** `uvicorn ok`

---

## 1.1 왜 FastAPI인가요?
입문자에게 FastAPI는 아주 매력적인 도구입니다. 
*   **빠릅니다:** 파이썬에서 가장 빠른 프레임워크 중 하나입니다.
*   **쉽습니다:** 코드가 직관적이고 표준 파이썬 타입을 활용합니다.
*   **자동 문서화:** 코드를 짜기만 해도 API 문서(Swagger)가 자동으로 만들어집니다.

---

## 1.2 핵심 코드 보기 (`main.py`)

가장 먼저 프로젝트의 심장부인 `main.py`를 작성했습니다.

```python
from fastapi import FastAPI

# FastAPI 인스턴스 생성
app = FastAPI()

@app.get("/")
async def root():
    """
    메인 페이지("/")에 접속했을 때 실행되는 함수입니다.
    """
    return {"message": "Hello World"}
```

### 💡 코드 설명
1.  `app = FastAPI()`: 우리의 웹 애플리케이션 객체를 만듭니다. 모든 요청은 이 `app` 객체를 통하게 됩니다.
2.  `@app.get("/")`: 사용자가 웹 브라우저 주소창에 `http://localhost:8000/`을 입력했을 때(GET 방식 요청) 이 아래의 함수를 실행하라는 뜻입니다. 이를 **라우팅(Routing)**이라고 합니다.
3.  `async def root()`: 비동기(Async) 처리를 지원하는 함수입니다. FastAPI의 강력한 장점 중 하나죠.
4.  `return {"message": "Hello World"}`: 브라우저에 JSON 형식의 데이터를 돌려줍니다.

---

## 1.3 데이터베이스 준비 (`database.py`)

아직 본격적으로 쓰지는 않지만, 데이터를 저장하기 위한 기초 설정을 마쳤습니다.

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 데이터베이스 파일 위치 설정 (SQLite 사용)
SQLALCHEMY_DATABASE_URL = "sqlite:///./myapi.db"

# 엔진 생성
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 데이터베이스 세션 생성 도구
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모델의 기반이 되는 클래스
Base = declarative_base()
```

---

## 1.4 서버 실행하기: Uvicorn이란?

FastAPI는 스스로 서버를 돌릴 수 없습니다. 그래서 **Uvicorn**이라는 "서버 도우미"가 필요합니다. 

터미널에서 아래 명령어를 입력해 서버를 실행할 수 있습니다.

```bash
uvicorn main:app --reload
```

*   `main`: `main.py` 파일을 의미합니다.
*   `app`: `main.py` 안에서 우리가 만든 `app = FastAPI()` 객체를 의미합니다.
*   `--reload`: 코드가 수정될 때마다 서버를 자동으로 다시 시작해 주는 아주 편리한 옵션입니다.

---

## 🛠 초보자를 위한 트러블슈팅

**Q: `uvicorn` 명령어를 입력했는데 찾을 수 없다고 나와요!**
A: 파이썬 가상환경(`venv`)이 활성화되어 있는지, 그리고 `pip install fastapi uvicorn`을 통해 필요한 패키지를 설치했는지 확인해 보세요.

**Q: 서버가 켜졌는데 어떻게 확인하나요?**
A: 브라우저를 열고 `http://127.0.0.1:8000`에 접속해 보세요. `{"message": "Hello World"}`가 보인다면 성공입니다! 또한 `http://127.0.0.1:8000/docs`에 접속하면 자동으로 생성된 멋진 API 문서를 볼 수 있습니다.

---
[다음 장으로 이동: 제2장 데이터베이스의 시작](./Chapter_02_Database_Connection.md)
