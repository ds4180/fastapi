from fastapi import APIRouter, Depends, HTTPException, Cookie, Body, Request
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
ACCESS_TOKEN_EXPIRE_MINUTES = 5 # 테스트를 위한 단축 설정: 5분 (기존 1시간)
REFRESH_TOKEN_EXPIRE_DAYS = 3     # 합의 설정: 3일
SECRET_KEY = "cceb75393b383115054b2195c59b3d4a5a948c8c530182855f0610b6a59083ad" 
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login", auto_error=False)

# --- [공통 지능형 권한 체커] ---

class RankChecker:
    """사용자의 Rank 등급을 동적으로 체크하는 공통 의존성"""
    def __init__(self, required_rank: int):
        self.required_rank = required_rank

    def __call__(self, current_user: User = Depends(get_db)):
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
        rtype = rd.type(redis_key)
        if rtype not in [b'string', 'string', b'none', 'none']:
            rd.delete(redis_key)

        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.device_category == device_category,
            UserSession.status == "ACTIVE"
        ).update({"status": "KICKED_OUT", "logout_at": datetime.now()})

        db_session = UserSession(
            user_id=user.id, session_key=jti, device_category=device_category,
            status="ACTIVE", login_at=datetime.now()
        )
        db.add(db_session)
        db.commit()

        rd.set(redis_key, jti, ex=60*60*24*REFRESH_TOKEN_EXPIRE_DAYS)
        
    except Exception as e:
        print(f"Session error: {e}")

    # Access Token 생성
    access_token_data = {
        "sub": user.username, "jti": jti, "category": device_category, "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    # Refresh Token 생성
    refresh_token_data = {
        "sub": user.username, "jti": jti, "category": device_category, "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    }

    return {
        "access_token": jwt.encode(access_token_data, SECRET_KEY, algorithm=ALGORITHM),
        "refresh_token": jwt.encode(refresh_token_data, SECRET_KEY, algorithm=ALGORITHM),
        "token_type": "bearer", 
        "username": user.username
    }

@router.post("/refresh", response_model=user_schema.TokenResponse)
def refresh_access_token(request: Request,
                         authorization: Optional[str] = Depends(oauth2_scheme),
                         refresh_token_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
                         db: Session = Depends(get_db)):
    """Refresh Token을 사용하여 새로운 Access Token 및 연장된 Refresh Token 발급"""
    token = None
    if authorization:
        token = authorization
    elif refresh_token_cookie:
        token = refresh_token_cookie
    
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token is missing")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        username = payload.get("sub")
        jti = payload.get("jti")
        category = payload.get("category")
        
        user = user_crud.get_user(db, username=username)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # 🚨 [중요] 세션 검증 (밀려났는지 확인)
        redis_key = f"session:{user.id}:{category}"
        active_jti = rd.get(redis_key)
        active_jti_str = active_jti.decode() if isinstance(active_jti, bytes) else active_jti
        
        if active_jti_str != jti:
            raise HTTPException(status_code=401, detail="Session expired or kicked out")

        # 활동 중이므로 Redis 세션 만료 시간을 다시 3일로 연장
        rd.expire(redis_key, 60*60*24*REFRESH_TOKEN_EXPIRE_DAYS)

        # 2. 새로운 Access Token 생성
        access_token_data = {
            "sub": user.username, "jti": jti, "category": category, "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        # 3. 새로운 Refresh Token 생성 (Sliding Window: 만료 시간 재연장)
        refresh_token_data = {
            "sub": user.username, "jti": jti, "category": category, "type": "refresh",
            "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        }

        return {
            "access_token": jwt.encode(access_token_data, SECRET_KEY, algorithm=ALGORITHM),
            "refresh_token": jwt.encode(refresh_token_data, SECRET_KEY, algorithm=ALGORITHM),
            "token_type": "bearer",
            "username": user.username
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token expired or invalid")

def get_current_user(token: Optional[str] = Depends(oauth2_scheme),
                     access_token: Optional[str] = Cookie(None),
                     db: Session = Depends(get_db)):
    final_token = token or access_token
    if not final_token: raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "refresh":
             raise HTTPException(status_code=401, detail="Access token required")

        username, jti, category = payload.get("sub"), payload.get("jti"), payload.get("category")
        user = user_crud.get_user(db, username=username)
        if not user: raise HTTPException(status_code=401)
        
        redis_key = f"session:{user.id}:{category}"
        active_jti = rd.get(redis_key)
        active_jti_str = active_jti.decode() if isinstance(active_jti, bytes) else active_jti
        
        if active_jti_str is None or active_jti_str != jti:
            raise HTTPException(status_code=401, detail="다른 기기에서 로그인하여 접속이 종료되었습니다.")
            
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="인증이 만료되었습니다.")

@router.post("/create", response_model=user_schema.User, status_code=status.HTTP_201_CREATED)
def create_user(user_create: user_schema.UserCreate, db: Session = Depends(get_db)):
    db_user = user_crud.get_existing_user(db, user_create=user_create)
    if db_user:
        raise HTTPException(status_code=409, detail="이미 등록된 사용자입니다.")
    return user_crud.create_user(db=db, user_create=user_create)

def get_current_user_optional(token: Optional[str] = Depends(oauth2_scheme),
                              access_token: Optional[str] = Cookie(None),
                              db: Session = Depends(get_db)):
    final_token = token or access_token
    if not final_token: return None
    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "refresh": return None
        
        username, jti, category = payload.get("sub"), payload.get("jti"), payload.get("category")
        user = user_crud.get_user(db, username=username)
        if not user: return None
        
        redis_key = f"session:{user.id}:{category}"
        active_jti = rd.get(redis_key)
        active_jti_str = active_jti.decode() if isinstance(active_jti, bytes) else active_jti
        
        if active_jti_str != jti: return None
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
    
    result = user_crud.kick_session(db, session_id=session_id)
    if result:
        return {"message": "success"}
    return {"error": "Session not found"}

@router.post("/logout")
def logout(token: Optional[str] = Depends(oauth2_scheme),
           access_token: Optional[str] = Cookie(None),
           db: Session = Depends(get_db)):
    final_token = token or access_token
    if not final_token: return {"message": "success"}
    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        jti, uid, cat = payload.get("jti"), payload.get("sub"), payload.get("category")
        user = user_crud.get_user(db, username=uid)
        if user:
            rd.delete(f"session:{user.id}:{cat}")
            db.query(UserSession).filter(UserSession.session_key == jti).update({
                "status": "LOGOUT", "logout_at": datetime.now()
            })
            db.commit()
    except: pass
    return {"message": "success"}

@router.get("/list", response_model=user_schema.UserList)
def user_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"users": user_crud.get_user_list(db)}
