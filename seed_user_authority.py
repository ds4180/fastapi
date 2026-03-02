from sqlalchemy.orm import Session
from database import SessionLocal
from models import User, UserProfile, BoardConfig

def seed_user_authority():
    db = SessionLocal()
    try:
        # 1. 모든 기존 유저에 대해 프로필 생성
        users = db.query(User).all()
        for i, user in enumerate(users):
            if not user.profile:
                # 첫 번째 유저는 최고 관리자(L3), 나머지는 운전원(0)으로 설정
                rank = 3 if i == 0 else 0
                profile = UserProfile(
                    user_id=user.id,
                    rank_level=rank,
                    is_active=True,
                    employee_no=f"EMP{user.id:04d}"
                )
                db.add(profile)
                print(f"Created profile for user: {user.username} (Rank: {rank})")
            else:
                print(f"Profile already exists for user: {user.username}")
        
        # 2. 기존 BoardConfig 권한 체계 업데이트 (신규 표준 반영)
        landing_board = db.query(BoardConfig).filter(BoardConfig.slug == "landing").first()
        if landing_board:
            landing_board.perm_read = {
                "ROLE_DRIVER": "GLOBAL",
                "ROLE_STAFF_L1": "GLOBAL",
                "ROLE_STAFF_L2": "GLOBAL",
                "ROLE_ADMIN": "GLOBAL"
            }
            landing_board.perm_write = {
                "ROLE_ADMIN": "GLOBAL"
            }
            print("Updated 'landing' board permissions.")

        db.commit()
        print("Successfully initialized user authority and updated board configurations!")
        
    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_user_authority()
