from database import SessionLocal
from models import User

def test_user_properties():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if user:
            print(f"Username: {user.username}")
            print(f"Rank Level: {user.rank}")
            print(f"Role: {user.role}")
        else:
            print("No users found.")
    finally:
        db.close()

if __name__ == "__main__":
    test_user_properties()
