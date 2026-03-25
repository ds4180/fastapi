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

@router.post("/login")
def login_for_access_token(response: Response, request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = user_crud.get_user(db, username=form_data.username)
    if not user or not user_crud.pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다.")

    # User-Agent를 통한 디바이스 유형 분석
    user_agent = request.headers.get("user-agent", "").lower()
    if "mobi" in user_agent or "android" in user_agent or "iphone" in user_agent:
        device_category = "MOBILE"
    else:
        device_category = "DESKTOP"

    # 밀어내기 로직: 기존 세션 삭제
    redis_key = f"session:{user.id}:{device_category}"
    old_jti = rd.get(redis_key)
    if old_jti:
        # DB의 기존 세션 상태 업데이트 (선택적)
        db.query(UserSession).filter(UserSession.session_key == old_jti).update({"status": "KICKED_OUT", "logout_at": datetime.now()})
        db.commit()

    # 새 세션 생성
    jti = str(uuid.uuid4())
    rd.set(redis_key, jti, ex=60*60*24*REFRESH_TOKEN_EXPIRE_DAYS)

    # DB에 새 세션 기록
    db_session = UserSession(
        user_id=user.id, session_key=jti, device_category=device_category,
        status="ACTIVE", login_at=datetime.now()
    )
    db.add(db_session)
    db.commit()
    
    # httpOnly 쿠키에 세션 ID 설정
    response.set_cookie(
        key="session_id",
        value=jti,
        httponly=True,
        max_age=60*60*24*REFRESH_TOKEN_EXPIRE_DAYS,
        samesite="lax",
        secure=False # 개발 환경에서는 False, 프로덕션에서는 True
    )
    
    return {"message": "Login successful", "username": user.username}



def get_current_user(request: Request, session_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    # User-Agent를 통한 디바이스 유형 분석
    user_agent = request.headers.get("user-agent", "").lower()
    if "mobi" in user_agent or "android" in user_agent or "iphone" in user_agent:
        device_category = "MOBILE"
    else:
        device_category = "DESKTOP"

    # DB에서 세션 정보를 조회하여 user_id를 찾음
    db_session = db.query(UserSession).filter(UserSession.session_key == session_id).first()
    if not db_session or db_session.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="세션이 유효하지 않습니다.")
        
    user = db.query(User).filter(User.id == db_session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    # Redis에서 세션 유효성 검증
    redis_key = f"session:{user.id}:{device_category}"
    active_jti = rd.get(redis_key)
    
    if active_jti is None or active_jti != session_id:
        # DB 세션 상태를 EXPIRED로 업데이트 (선택적)
        db_session.status = "EXPIRED"
        db.commit()
        raise HTTPException(status_code=401, detail="다른 기기에서 로그인하여 접속이 종료되었습니다.")
        
    # 세션 만료 시간 연장 (활동 기준)
    rd.expire(redis_key, 60*60*24*REFRESH_TOKEN_EXPIRE_DAYS)
    
    return user

@router.post("/create", response_model=user_schema.User, status_code=status.HTTP_201_CREATED)
def create_user(user_create: user_schema.UserCreate, db: Session = Depends(get_db)):
    db_user = user_crud.get_existing_user(db, user_create=user_create)
    if db_user:
        raise HTTPException(status_code=409, detail="이미 등록된 사용자입니다.")
    return user_crud.create_user(db=db, user_create=user_create)

def get_current_user_optional(request: Request, session_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not session_id:
        return None

    try:
        user_agent = request.headers.get("user-agent", "").lower()
        device_category = "MOBILE" if "mobi" in user_agent or "android" in user_agent or "iphone" in user_agent else "DESKTOP"

        db_session = db.query(UserSession).filter(UserSession.session_key == session_id, UserSession.status == "ACTIVE").first()
        if not db_session:
            return None
            
        user = db.query(User).filter(User.id == db_session.user_id).first()
        if not user:
            return None

        redis_key = f"session:{user.id}:{device_category}"
        active_jti = rd.get(redis_key)
        
        if active_jti is None or active_jti != session_id:
            return None
            
        rd.expire(redis_key, 60*60*24*REFRESH_TOKEN_EXPIRE_DAYS)
        return user
    except Exception:
        return None

@router.get("/me", response_model=user_schema.User)
def read_users_me(current_user: User = Depends(get_current_user)):
    rank_val = current_user.rank() if callable(current_user.rank) else current_user.rank
    return user_schema.User(id=current_user.id, username=current_user.username, email=current_user.email, rank_level=rank_val)

@router.get("/sessions", response_model=List[user_schema.UserSessionResponse])
def session_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return user_crud.get_session_list(db)

@router.post("/sessions/kick/{target_session_id}")
def kick_user_session(target_session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    if user_rank < 4: raise HTTPException(status_code=403)
    
    result = user_crud.kick_session(db, session_id=target_session_id)
    if result:
        return {"message": "success"}
    return {"error": "Session not found"}

@router.post("/logout")
def logout(response: Response, session_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if session_id:
        db_session = db.query(UserSession).filter(UserSession.session_key == session_id).first()
        if db_session:
            # Redis에서 세션 삭제
            redis_key = f"session:{db_session.user_id}:{db_session.device_category}"
            rd.delete(redis_key)
            
            # DB 세션 상태 업데이트
            db_session.status = "LOGOUT"
            db_session.logout_at = datetime.now()
            db.commit()

    # 클라이언트의 쿠키 삭제
    response.delete_cookie(key="session_id")
    return {"message": "Logout successful"}

@router.get("/list", response_model=user_schema.UserList)
def user_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"users": user_crud.get_user_list(db)}
