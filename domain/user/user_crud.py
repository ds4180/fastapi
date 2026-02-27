from passlib.context import CryptContext
from datetime import datetime

from sqlalchemy.orm import Session
from domain.user.user_schema import UserCreate
from models import User, UserSession
from redis_config import rd

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_session_list(db: Session, limit: int = 50):
    """최근 접속순으로 세션 목록 조회"""
    sessions = db.query(UserSession).join(User).order_by(UserSession.login_at.desc()).limit(limit).all()
    # Pydantic 응답을 위해 username을 추가로 담아줍니다.
    for s in sessions:
        s.username = s.user.username
    return sessions

def kick_session(db: Session, session_id: int):
    """특정 세션을 강제로 쫓아냅니다."""
    db_session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not db_session:
        return None
    
    # 1. DB 상태 변경
    db_session.status = "KICKED_OUT"
    db_session.logout_at = datetime.now()
    db.commit()

    # 2. Redis에서 해당 슬롯 삭제 (즉시 차단)
    # 현재 로그인 로직에서 session:{user_id}:{category} 키를 사용하고 있습니다.
    # 만약 Redis에 저장된 jti가 이 세션의 jti와 같다면 삭제합니다.
    redis_key = f"session:{db_session.user_id}:{db_session.device_category}"
    active_jti = rd.get(redis_key)
    
    if active_jti == db_session.session_key:
        rd.delete(redis_key)
        
    return db_session

def get_existing_user(db: Session, user_create: UserCreate):
    return db.query(User).filter(
        (User.username == user_create.username) |
        (User.email == user_create.email)
    ).first()

def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)



def create_user(db: Session, user_create: UserCreate):
    db_user = User(username=user_create.username, 
                   password=pwd_context.hash(user_create.password1),
                   email=user_create.email)
    db.add(db_user)
    db.commit()

def get_user_list(db: Session):
    return db.query(User).all()
