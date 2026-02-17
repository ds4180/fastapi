# 제2장: 데이터베이스의 시작 📁
> **학습 목표:** 데이터의 구조(Model)를 정의하고, 데이터베이스와 연결하여 실제 테이블을 생성할 준비를 합니다.

## 📌 이번 장에서 다루는 커밋
*   **Hash:** `8d86424`
*   **Message:** `DB connetion OK`

---

## 2.1 데이터의 모양 정하기: 모델(Model)
컴퓨터에게 "질문"과 "답변"이 각각 어떤 정보를 담고 있는지 알려줘야 합니다. 이를 **모델(Model)**이라고 부릅니다.

### `models.py` 들여다보기
```python
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship 
from database import Base

class Question(Base):
    __tablename__ ="question"

    id = Column(Integer, primary_key=True) # 고유 번호
    subject = Column(String, nullable=False) # 제목
    content = Column(Text, nullable=False) # 내용
    create_date = Column(DateTime, nullable=False) # 작성일

class Answer(Base):
    __tablename__ = "answer"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    create_date = Column(DateTime, nullable=False)
    # 질문과 연결 (외래키)
    question_id = Column(Integer, ForeignKey('question.id'))
    # 답변에서 질문 정보를 바로 참조할 수 있게 함
    question = relationship('Question')
```

### 💡 핵심 개념 설명
1.  **Integer, String, Text**: 데이터의 종류입니다. 숫자인지, 짧은 글인지, 긴 본문인지 정합니다.
2.  **primary_key=True**: 각 데이터를 구분할 수 있는 '유일한 식별값'입니다. (ID 카드 번호 같은 역할)
3.  **ForeignKey**: 답변(`Answer`)이 어떤 질문(`Question`)에 달린 것인지 연결해 주는 고리입니다.
4.  **relationship**: 파이썬 코드 상에서 질문 객체를 통해 답변을 찾거나, 답변을 통해 질문을 편하게 불러오기 위한 설정입니다.

---

## 2.2 DB 연결 파일 업데이트 (`database.py`)
이전 장에서 만들었던 파일에서 데이터베이스 이름이 `myapi.db`에서 `bus1942.db`로 구체화되었습니다.

```python
SQLALCHEMY_DATABASE_URL = "sqlite:///./bus1942.db"
```
*   **SQLite**: 복잡한 설치 없이 파일 하나로 데이터베이스를 운영할 수 있어 초보자에게 가장 권장되는 DB입니다.

---

## 2.3 Alembic: 데이터베이스의 타임머신
코드로 모델을 만들었다고 해서 바로 프로그램이 작동하는 것은 아닙니다. 이 모델 정보를 실제 데이터베이스 파일(`bus1942.db`)에 "반영"하는 과정이 필요합니다.

이때 사용하는 도구가 **Alembic**입니다. 이번 커밋에서는 Alembic을 설정하는 파일(`alembic.ini`, `migrations/env.py`)들이 추가되었습니다.

### 🚀 마이그레이션 순서 (초보자 권장)
1.  `alembic init migrations`: 초기 설정 (이미 되어 있음)
2.  `alembic revision --autogenerate -m "메시지"`: 모델의 변경 사항을 감지하여 기록 생성
3.  `alembic upgrade head`: 기록된 변경 사항을 실제 DB 파일에 적용

---

## 🛠 초보자를 위한 트러블슈팅

**Q: `nullable=False`는 무슨 뜻인가요?**
A: "이 칸은 비워둘 수 없다"는 뜻입니다. 제목이나 내용 없이 글을 쓸 수는 없으니까요!

**Q: 데이터베이스 파일을 직접 열어보고 싶어요.**
A: 'DB Browser for SQLite' 같은 무료 프로그램을 설치하면 `bus1942.db` 파일을 열어 표 형태로 데이터를 직접 확인할 수 있습니다.

---
[이전 장으로: 제1장 Hello FastAPI!](./Chapter_01_Hello_FastAPI.md) | [다음 장으로: 제3장 질문 목록과 상세 페이지](./Chapter_03_Question_List_Detail.md)
