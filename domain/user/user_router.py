from fastapi import APIRouter, Depends, HTTPException
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

# JWT 설정 (기존 안정 버전 값 유지)
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1일
SECRET_KEY = "cceb75393b383115054b2195c59b3d4a5a948c8c530182855f0610b6a59083ad" 
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")

@router.post("/login", response_model=user_schema.TokenResponse)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),
                           device_category: str = "WORKSPACE",
                           db: Session = Depends(get_db)):
    """
    안정 버전의 로그인 로직 + 폼 데이터 수신 방식
    """
    # 1. 사용자 확인
    user = user_crud.get_user(db, username=form_data.username)
    if not user or not user_crud.pwd_context.verify(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 틀렸습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 고유 식별자(JTI) 생성
    jti = str(uuid.uuid4())

    # 3. 세션 관리 (Redis & DB)
    try:
        # 기존 ACTIVE 세션들을 밀어냄 (같은 카테고리)
        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.device_category == device_category,
            UserSession.status == "ACTIVE"
        ).update({"status": "KICKED_OUT", "logout_at": datetime.now()})

        # 새 세션 등록
        db_session = UserSession(
            user_id=user.id,
            session_key=jti,
            device_category=device_category,
            status="ACTIVE",
            login_at=datetime.now()
        )
        db.add(db_session)
        db.commit()

        # Redis 슬롯 점유 (7일)
        redis_key = f"session:{user.id}:{device_category}"
        rd.set(redis_key, jti, ex=60*60*24*7)
        
    except Exception as e:
        print(f"Session management error: {e}")

    # 4. 토큰 생성
    access_token_data = {
        "sub": user.username,
        "jti": jti,
        "category": device_category,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    access_token = jwt.encode(access_token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": "not_used_in_this_flow",
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
            
        user = user_crud.get_user(db, username=username)
        if user is None:
            raise credentials_exception

        # Redis 세션 검증
        redis_key = f"session:{user.id}:{category}"
        active_jti = rd.get(redis_key)
        
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

@router.get("/me", response_model=user_schema.User)
def read_users_me(current_user: User = Depends(get_current_user)):
    """현재 로그인한 유저 정보 (rank_level 포함)"""
    return user_schema.User(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        rank_level=current_user.rank
    )

@router.get("/sessions", response_model=list[user_schema.UserSessionResponse])
def session_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return user_crud.get_session_list(db)

@router.get("/list", response_model=user_schema.UserList)
def user_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    users = user_crud.get_user_list(db)
    return {"users": users}
