
from sqlalchemy.orm import Session
from database import SessionLocal
from models import BoardConfig, Post, User
from datetime import datetime

def seed_data():
    db = SessionLocal()
    try:
        # 1. 기존 데이터 유무 확인 (중복 방지)
        existing_board = db.query(BoardConfig).filter(BoardConfig.slug == "landing").first()
        if existing_board:
            print("Already seeded. Skipping...")
            return

        # 2. 대문용 보드 설정 생성
        landing_board = BoardConfig(
            slug="landing",
            name="메인 대문",
            description="사이트의 메인 랜딩 페이지를 관리하는 보드입니다.",
            layout_type="landing",
            items_per_page=1,
            fields_def=[],
            options={"use_comment": False, "use_upload": False},
            perm_read={"roles": ["GUEST", "USER"]},
            perm_write={"roles": ["ADMIN"]},
            is_active=True
        )
        db.add(landing_board)
        db.flush() # ID를 얻기 위해 flush

        # 3. 작성자(User) 확인 (첫 번째 유저 가져오기)
        user = db.query(User).first()
        user_id = user.id if user else None

        # 4. 첫 번째 대문 포스트 생성 (TipTap JSON 구조 예시)
        welcome_post = Post(
            board_id=landing_board.id,
            user_id=user_id,
            title="나만의 CMS v1 프로젝트에 오신 것을 환영합니다!",
            content_json={
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 2},
                        "content": [{"type": "text", "text": "🚀 새로운 시작"}]
                    },
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "이 콘텐츠는 이제 DB에서 관리됩니다. 코드를 수정하지 않고도 관리자 페이지에서 이 내용을 마음대로 바꿀 수 있습니다."}
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "유연한 JSONB 데이터 구조"}]}]},
                            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "모듈형 기능 스위치"}]}]},
                            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "실시간 데이터 동기화"}]}]}
                        ]
                    }
                ]
            },
            extra_data={"highlight_color": "#0d6efd"},
            status="published",
            create_date=datetime.now()
        )
        db.add(welcome_post)
        
        db.commit()
        print("Successfully seeded CMS v1 initial data!")
        
    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
