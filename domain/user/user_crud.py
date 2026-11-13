# 현대적 패스워드 해싱 표준 라이브러리 pwdlib 적용 (방치된 passlib 대체 및 최신 bcrypt 보안 호환)
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from datetime import datetime
from typing import Union

from sqlalchemy.orm import Session
from domain.user.user_schema import UserCreate
from models import User, UserSession, UserProfile # UserProfile 임포트 추가
from redis_config import rd

# 기존 bcrypt 해시 데이터와 100% 완벽 호환되도록 BcryptHasher 적용
# pwd_context.verify(), pwd_context.hash() 인터페이스가 그대로 유지되어 기존 호출부 수정 없이 동작
pwd_context = PasswordHash((BcryptHasher(),))

# 🛡️ [보안 강화 4 - 타이밍 공격(Timing Attack) 및 계정 열거(Username Enumeration) 방어용 더미 해시]:
# 존재하지 않는 아이디(username)로 로그인을 시도할 때 bcrypt 해시 검증을 건너뛰고 즉시 401을 반환하면,
# 응답 시간 차이(존재하지 않는 계정: ~1ms vs 존재하는 계정: ~150ms)를 측정해 사내 유효 아이디 목록을
# 전수 추출할 수 있습니다. 이를 막기 위해 계정이 없을 때도 아래 더미 해시를 동일하게 검증합니다.
DUMMY_PASSWORD_HASH = pwd_context.hash("__jeju_live_constant_time_dummy_secret__")


def verify_user_credentials(user: Union[User, None], plain_password: str) -> bool:
    """
    [Constant-Time 자격증명 검증기]
    계정 존재 여부와 무관하게 항상 동일한 bcrypt 해시 연산 시간을 소요하여
    타이밍 공격(Timing Attack)을 통한 사내 계정 아이디 유추를 원천 차단합니다.
    """
    if user is None or not getattr(user, "password", None):
        # 계정이 존재하지 않아도 더미 해시 검증을 수행하여 동일한 CPU 연산 시간 소모 후 False 반환
        pwd_context.verify(plain_password, DUMMY_PASSWORD_HASH)
        return False
    return pwd_context.verify(plain_password, user.password)


def get_session_list(db: Session, limit: int = 100):
    """최근 접속순으로 세션 목록 조회 및 통합 자가치유 동기화 (최대 100개)"""
    from core.session import sync_expired_sessions

    sync_expired_sessions(db)
    sessions = db.query(UserSession).join(User).order_by(UserSession.login_at.desc()).limit(limit).all()

    for s in sessions:
        s.username = s.user.username

    return sessions

def kick_session(db: Session, session_id: Union[int, str]):
    """특정 세션을 강제로 쫓아냅니다 (ID 또는 session_key 모두 지원)."""
    db_session = None
    if isinstance(session_id, int) or (isinstance(session_id, str) and session_id.isdigit()):
        db_session = db.query(UserSession).filter(UserSession.id == int(session_id)).first()

    if not db_session and isinstance(session_id, str):
        db_session = db.query(UserSession).filter(UserSession.session_key == session_id).first()

    if not db_session:
        return None

    # 1. DB 상태 변경
    db_session.status = "KICKED_OUT"
    db_session.logout_at = datetime.now()
    db.commit()

    # 2. Redis Set에서 해당 JTI 삭제
    redis_key = f"session:{db_session.user_id}:{db_session.device_category}"
    rd.srem(redis_key, db_session.session_key)

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
    # 1. User 생성
    db_user = User(username=user_create.username, 
                   password=pwd_context.hash(user_create.password1),
                   email=user_create.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user) # ID 할당을 위해 refresh

    # 2. UserProfile 생성 (기본 Rank 0 부여)
    db_profile = UserProfile(user_id=db_user.id) # rank_level은 default=0 적용
    db.add(db_profile)
    db.commit()
    return db_user # 생성된 User 객체 반환

def get_user_list(db: Session):
    return db.query(User).all()
