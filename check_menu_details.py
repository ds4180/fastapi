from database import SessionLocal
from models import Menu, BoardConfig

db = SessionLocal()
print(f"{'ID':<5} | {'Title':<15} | {'Board ID':<10} | {'Slug':<15} | {'Min Rank':<10} | {'URL'}")
print("-" * 80)
menus = db.query(Menu).all()
for m in menus:
    slug = "N/A"
    if m.board_id:
        board = db.query(BoardConfig).filter(BoardConfig.id == m.board_id).first()
        if board:
            slug = board.slug
    print(f"{m.id:<5} | {m.title:<15} | {str(m.board_id):<10} | {slug:<15} | {m.min_rank:<10} | {m.external_url}")

db.close()
