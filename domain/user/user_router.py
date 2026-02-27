from fastapi import APIRouter
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from starlette import status

from database import get_db
from domain.user import user_schema, user_crud
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
import uuid
from redis_config import rd
from models import User, UserSession

router = APIRouter(
    prefix="/users",
)


# JWT 설정
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1일 (편의를 위해 늘림)
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7일
SECRET_KEY = "cceb75393b383115054b2195c59b3d4a5a948c8c530182855f0610b6a59083ad" 
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")

@router.post("/login", response_model=user_schema.TokenResponse)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),
                           device_category: str = "WORKSPACE", # MOBILE 또는 WORKSPACE (기본값)
                           db: Session = Depends(get_db)):

    # 1. 사용자 확인
    user = user_crud.get_user(db, username=form_data.username)
    if not user or not user_crud.verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 틀렸습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 고유 식별자(JTI) 생성 - 이 세션의 '입장권 번호'
    jti = str(uuid.uuid4())

    # 3. 🚨 지능형 슬롯 관리 (Redis & DB 로그)
    # 기존 슬롯 비우기 (밀어내기) 및 새 로그 기록
    try:
        # DB에 세션 로그 기록
        db_session = UserSession(
            user_id=user.id,
            session_key=jti,
            device_category=device_category,
            status="ACTIVE",
            login_at=datetime.now()
        )
        db.add(db_session)
        
        # 같은 카테고리의 기존 ACTIVE 세션들을 밀어냄 (DB 업데이트)
        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.device_category == device_category,
            UserSession.status == "ACTIVE"
        ).update({"status": "KICKED_OUT", "logout_at": datetime.now()})
        
        db.commit()

        # Redis 슬롯 점유 (7일간 유효)
        redis_key = f"session:{user.id}:{device_category}"
        rd.set(redis_key, jti, ex=60*60*24*7)
        
    except Exception as e:
        print(f"Session management error: {e}")
        # 세션 기록에 실패해도 로그인은 시켜주되 로그는 남깁니다.

    # 4. 토큰 생성 (JTI와 카테고리 포함)
    access_token_data = {
        "sub": user.username,
        "jti": jti,
        "category": device_category,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    access_token = jwt.encode(access_token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": "not_used_in_this_flow", # 단순화를 위해 일단 고정값
        "token_type": "bearer",
        "username": user.username
    }

def get_current_user(token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")
        category: str = payload.get("category")
        
        if username is None or jti is None or category is None:
            raise credentials_exception
            
        # 1. 유저를 먼저 찾습니다 (DB 조회 1회)
        user = user_crud.get_user(db, username=username)
        if user is None:
            raise credentials_exception

        # 2. Redis 세션 검증 (밀려났는지 확인)
        redis_key = f"session:{user.id}:{category}"
        active_jti = rd.get(redis_key)
        
        # Redis에 데이터가 없거나(만료), 내 jti와 다르다면(밀려남)
        if active_jti is None or active_jti != jti:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="다른 기기에서 로그인하여 접속이 종료되었습니다.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return user

    except JWTError:
        raise credentials_exception

def get_current_user_optional(token: str = Depends(oauth2_scheme),
                              db: Session = Depends(get_db)):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    else:
        return user_crud.get_user(db, username=username)
@router.get("/sessions", response_model=list[user_schema.UserSessionResponse])
def session_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    모든 사용자의 접속 기록 및 현재 접속 현황을 조회합니다.
    """
    return user_crud.get_session_list(db)

@router.post("/sessions/kick/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def session_kick(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    특정 기기의 세션을 강제로 쫓아냅니다. (Kicking Out)
    """
    result = user_crud.kick_session(db, session_id=session_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다.")
    return None

@router.get("/list", response_model=user_schema.UserList)
def user_list(db: Session = Depends(get_db)):
    users = user_crud.get_user_list(db)
    return {"users": users}
