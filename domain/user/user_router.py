from fastapi import APIRouter, Depends, HTTPException, Cookie, Body, Request, Response
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from starlette import status
from typing import Optional, List

from database import get_db
from domain.user import user_schema, user_crud
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
import uuid
from redis_config import rd
from models import User, UserSession

router = APIRouter(prefix="/users")

# JWT 및 세션 정책
REFRESH_TOKEN_EXPIRE_DAYS = 3  

# ----------------------------
# 1. 최상위 의존성 (다른 함수가 참조하므로 가장 먼저 정의)
# ----------------------------

def get_current_user(request: Request, session_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """필수 인증 의존성 + 슬라이딩 윈도우"""
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    db_session = db.query(UserSession).filter(UserSession.session_key == session_id).first()
    if not db_session or db_session.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="세션이 유효하지 않습니다.")
    
    db_session.last_activity = datetime.now()
    db.commit()

    user = db.query(User).filter(User.id == db_session.user_id).first()
    if not user: raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    redis_key = f"session:{user.id}:{db_session.device_category}"
    if not rd.sismember(redis_key, session_id):
        db_session.status = "EXPIRED"
        db.commit()
        raise HTTPException(status_code=401, detail="다른 기기에서 로그인하여 접속이 종료되었습니다.")
        
    rd.expire(redis_key, 60*60*24*REFRESH_TOKEN_EXPIRE_DAYS)
    return user

def get_current_user_optional(request: Request, session_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """선택적 인증 의존성"""
    if not session_id: return None
    try:
        user_agent = request.headers.get("user-agent", "").lower()
        device_category = "MOBILE" if any(x in user_agent for x in ["mobi", "android", "iphone"]) else "DESKTOP"
        db_session = db.query(UserSession).filter(UserSession.session_key == session_id, UserSession.status == "ACTIVE").first()
        if not db_session: return None
        user = db.query(User).filter(User.id == db_session.user_id).first()
        if not user: return None
        redis_key = f"session:{user.id}:{device_category}"
        if not rd.sismember(redis_key, session_id): return None
        rd.expire(redis_key, 60*60*24*REFRESH_TOKEN_EXPIRE_DAYS)
        return user
    except: return None

# ----------------------------
# 2. 권한 관련 클래스 및 데코레이터
# ----------------------------

class RankChecker:
    def __init__(self, required_rank: int):
        self.required_rank = required_rank
    def __call__(self, current_user: User = Depends(get_current_user)):
        user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
        if user_rank < self.required_rank:
            raise HTTPException(status_code=403, detail=f"권한 부족 (필수: {self.required_rank})")
        return current_user

def check_rank(required_rank: int):
    def _check(current_user: User = Depends(get_current_user)):
        user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
        if user_rank < required_rank:
            raise HTTPException(status_code=403, detail=f"권한 부족 (필수: {required_rank})")
        return current_user
    return _check

# ----------------------------
# 3. 라우터 엔드포인트들
# ----------------------------

@router.post("/login")
def login_for_access_token(response: Response, request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # ... (로그인 로직 동일) ...
    user = user_crud.get_user(db, username=form_data.username)
    if not user or not user_crud.pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다.")

    user_agent_full = request.headers.get("user-agent", "")
    ip_address = request.client.host
    device_category = "MOBILE" if any(x in user_agent_full.lower() for x in ["mobi", "android", "iphone"]) else "DESKTOP"

    redis_key = f"session:{user.id}:{device_category}"
    # 기존 세션이 있다면 해당 세션을 DB에서 만료 처리 및 Redis에서 삭제
    current_jtis = rd.smembers(redis_key)
    for jti_item in current_jtis:
        jti = jti_item.decode('utf-8') if isinstance(jti_item, bytes) else jti_item
        db.query(UserSession).filter(UserSession.session_key == jti).update({
            "status": "KICKED_OUT", "logout_at": datetime.now()
        })
        rd.srem(redis_key, jti)
    db.commit()

    jti = str(uuid.uuid4())
    rd.sadd(redis_key, jti)
    rd.expire(redis_key, 60*60*24*REFRESH_TOKEN_EXPIRE_DAYS)

    db_session = UserSession(
        user_id=user.id, session_key=jti, device_category=device_category,
        device_name=user_agent_full[:255], ip_address=ip_address,
        status="ACTIVE", login_at=datetime.now(), last_activity=datetime.now()
    )
    db.add(db_session)
    db.commit()
    
    response.set_cookie(key="session_id", value=jti, httponly=True, max_age=60*60*24*REFRESH_TOKEN_EXPIRE_DAYS, samesite="lax", secure=False)
    return {"message": "Login successful", "username": user.username}

@router.get("/me", response_model=user_schema.User)
def read_users_me(current_user: User = Depends(get_current_user)):
    rank_val = current_user.rank() if callable(current_user.rank) else current_user.rank
    return user_schema.User(id=current_user.id, username=current_user.username, email=current_user.email, rank_level=rank_val)

@router.post("/create", response_model=user_schema.User, status_code=status.HTTP_201_CREATED)
def create_user(user_create: user_schema.UserCreate, db: Session = Depends(get_db)):
    db_user = user_crud.get_existing_user(db, user_create=user_create)
    if db_user: raise HTTPException(status_code=409, detail="이미 등록된 사용자입니다.")
    return user_crud.create_user(db=db, user_create=user_create)

@router.get("/sessions", response_model=List[user_schema.UserSessionResponse])
def session_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return user_crud.get_session_list(db)

@router.post("/sessions/kick/{target_session_id}")
def kick_user_session(target_session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    if user_rank < 4: raise HTTPException(status_code=403, detail="권한 부족")
    result = user_crud.kick_session(db, session_id=target_session_id)
    return {"message": "success"} if result else {"error": "Session not found"}

@router.post("/logout")
def logout(response: Response, session_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if session_id:
        db_session = db.query(UserSession).filter(UserSession.session_key == session_id).first()
        if db_session:
            rd.srem(f"session:{db_session.user_id}:{db_session.device_category}", session_id)
            db_session.status = "LOGOUT"; db_session.logout_at = datetime.now(); db.commit()
    response.delete_cookie(key="session_id")
    return {"message": "Logout successful"}

@router.get("/list", response_model=user_schema.UserList)
def user_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"users": user_crud.get_user_list(db)}
