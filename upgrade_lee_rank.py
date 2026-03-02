from sqlalchemy.orm import Session
from database import SessionLocal
from models import User

def upgrade_user_rank(username: str, new_rank: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user:
            old_rank = user.rank
            user.rank = new_rank
            db.commit()
            print(f"SUCCESS: User '{username}' rank upgraded from {old_rank} to {new_rank}.")
        else:
            print(f"ERROR: User '{username}' not found.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    upgrade_user_rank("lee", 4)
