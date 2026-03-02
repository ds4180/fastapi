from fastapi import APIRouter, Depends, HTTPException, Cookie, Body
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

router = APIRouter(
    prefix="/users",
)

# JWT 및 세션 정책
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 
SECRET_KEY = "cceb75393b383115054b2195c59b3d4a5a948c8c530182855f0610b6a59083ad" 
ALGORITHM = "HS256"
MAX_SESSIONS_PER_CATEGORY = 2

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login", auto_error=False)

# --- [공통 지능형 권한 체커] ---

class RankChecker:
    """사용자의 Rank 등급을 동적으로 체크하는 공통 의존성"""
    def __init__(self, required_rank: int):
        self.required_rank = required_rank

    def __call__(self, current_user: User = Depends(get_db)): # 👈 아래 get_current_user를 직접 쓰기 위해 순서 조정
        # 이 메소드는 내부에서 get_current_user를 직접 호출하지 않고 
        # API 엔드포인트에서 Depends()로 엮어서 사용됩니다.
        pass

def check_rank(required_rank: int):
    """RankChecker 대용의 함수형 의존성 (더 유연함)"""
    def _check(current_user: User = Depends(get_current_user)):
        user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
        if user_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"접근 권한 부족 (필수 Rank: {required_rank})"
            )
        return current_user
    return _check

# ----------------------------

@router.post("/login", response_model=user_schema.TokenResponse)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),
                           device_category: str = "WORKSPACE",
                           db: Session = Depends(get_db)):
    user = user_crud.get_user(db, username=form_data.username)
    if not user or not user_crud.pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다.")

    jti = str(uuid.uuid4())
    redis_key = f"session:{user.id}:{device_category}"

    try:
        if rd.exists(redis_key) and rd.type(redis_key) != b'set':
            rd.delete(redis_key)
        rd.sadd(redis_key, jti)
        rd.expire(redis_key, 60*60*24*7)

        all_jtis = rd.smembers(redis_key)
        if len(all_jtis) > MAX_SESSIONS_PER_CATEGORY:
            removed_jti = rd.spop(redis_key)
            if removed_jti:
                db.query(UserSession).filter(UserSession.session_key == removed_jti.decode()).update({"status": "KICKED_OUT", "logout_at": datetime.now()})

        db_session = UserSession(
            user_id=user.id, session_key=jti, device_category=device_category,
            status="ACTIVE", login_at=datetime.now()
        )
        db.add(db_session)
        db.commit()
    except Exception as e:
        print(f"Session error: {e}")

    access_token_data = {
        "sub": user.username, "jti": jti, "category": device_category,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    return {
        "access_token": jwt.encode(access_token_data, SECRET_KEY, algorithm=ALGORITHM),
        "refresh_token": "not_used", "token_type": "bearer", "username": user.username
    }

def get_current_user(token: Optional[str] = Depends(oauth2_scheme),
                     access_token: Optional[str] = Cookie(None),
                     db: Session = Depends(get_db)):
    final_token = token or access_token
    if not final_token: raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        username, jti, category = payload.get("sub"), payload.get("jti"), payload.get("category")
        user = user_crud.get_user(db, username=username)
        if not user: raise HTTPException(status_code=401)
        if not rd.sismember(f"session:{user.id}:{category}", jti):
            raise HTTPException(status_code=401, detail="다른 기기에서 로그인하여 접속이 종료되었습니다.")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="인증이 만료되었습니다.")

def get_current_user_optional(token: Optional[str] = Depends(oauth2_scheme),
                              access_token: Optional[str] = Cookie(None),
                              db: Session = Depends(get_db)):
    final_token = token or access_token
    if not final_token: return None
    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        username, jti, category = payload.get("sub"), payload.get("jti"), payload.get("category")
        user = user_crud.get_user(db, username=username)
        if not user: return None
        if not rd.sismember(f"session:{user.id}:{category}", jti): return None
        return user
    except: return None

@router.get("/me", response_model=user_schema.User)
def read_users_me(current_user: User = Depends(get_current_user)):
    rank_val = current_user.rank() if callable(current_user.rank) else current_user.rank
    return user_schema.User(id=current_user.id, username=current_user.username, email=current_user.email, rank_level=rank_val)

@router.get("/sessions", response_model=List[user_schema.UserSessionResponse])
def session_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return user_crud.get_session_list(db)

@router.post("/sessions/kick/{session_id}")
def kick_user_session(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    if user_rank < 4: raise HTTPException(status_code=403)
    db_session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if db_session:
        rd.srem(f"session:{db_session.user_id}:{db_session.device_category}", db_session.session_key)
        db_session.status = "KICKED_OUT"
        db.commit()
        return {"message": "success"}
    return {"error": "Session not found"}

@router.get("/list", response_model=user_schema.UserList)
def user_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"users": user_crud.get_user_list(db)}
