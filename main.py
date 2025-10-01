from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from domain.question import question_router
from domain.answer import answer_router
from database import engine

from models import Base

app = FastAPI()

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://192.168.200.217:5173",
    "http://localhost:3000",  # 프로덕션 SvelteKit 서버 주소 추가
    "http://localhost", # Nginx를 통해 접속하는 주소
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/hello")
async def root():
    """
    Handles GET requests to the root endpoint.

    Returns:
        dict: A dictionary containing a greeting message.
    """

    return {"message": "Hello World"}

app.include_router(question_router.router)
app.include_router(answer_router.router)





def main():
    """
    main test Document

    
    """
    print("Hello from test!")


if __name__ == "__main__":
    main()
