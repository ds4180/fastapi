from database import SessionLocal
from models import User, Menu

db = SessionLocal()

# 1. 사용자 kim 정보 확인
user = db.query(User).filter(User.username == "kim").first()
if user:
    rank_val = user.rank() if callable(user.rank) else user.rank
    print(f"--- User Info ---")
    print(f"Username: {user.username}, Rank: {rank_val}")
else:
    # 모든 유저 검색
    print("User 'kim' not found. Searching all users...")
    all_users = db.query(User).all()
    for u in all_users:
        if u.username.lower() == "kim":
             rank_val = u.rank() if callable(u.rank) else u.rank
             print(f"Found match: {u.username}, Rank: {rank_val}")

# 2. 'field' 메뉴 정보 확인
menu = db.query(Menu).filter(Menu.title == "field").first()
if not menu:
    menu = db.query(Menu).filter(Menu.external_url.contains("field")).first()

if menu:
    print(f"\n--- Menu Info ---")
    print(f"Title: {menu.title}, Min Rank: {menu.min_rank}, Visible: {menu.is_visible}, URL: {menu.external_url}")
else:
    print(f"\nMenu with 'field' not found.")

db.close()
