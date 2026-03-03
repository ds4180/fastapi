from database import SessionLocal
from models import Menu, User

db = SessionLocal()
print("--- Menus ---")
menus = db.query(Menu).all()
print(f"{'ID':<5} | {'Title':<20} | {'Min Rank':<10} | {'External URL'}")
print("-" * 60)
for m in menus:
    print(f"{m.id:<5} | {m.title:<20} | {m.min_rank:<10} | {m.external_url}")

print("\n--- Users (First 5) ---")
users = db.query(User).limit(5).all()
for u in users:
    rank_val = u.rank() if callable(u.rank) else u.rank
    print(f"Username: {u.username}, Rank: {rank_val}")

db.close()
