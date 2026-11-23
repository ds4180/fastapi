from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional, Any

from database import get_db
from core.deps import get_current_user_optional
from core.exceptions import CoreException
from domain.v1.app.app_service import load_app_data

router = APIRouter(prefix="/v1/app", tags=["App Engine"])


@router.get("/data/{app_id}/{slug:path}")
def get_app_data(
    app_id: str,
    slug: str,
    request: Request,
    page: int = 0,
    size: int = 10,
    keyword: str = "",
    sort: str = "latest",
    db: Session = Depends(get_db),
    current_user: Optional[Any] = Depends(get_current_user_optional),
):
    """
    [Data-Driven] 범용 앱 데이터 제공 API
    AppRegistry의 설정에 따라 동적으로 모델을 탐색하고 서비스 바인딩을 조립합니다.
    """
    try:
        return load_app_data(
            db=db,
            app_id=app_id,
            slug=slug,
            request=request,
            current_user=current_user,
            page=page,
            size=size,
            keyword=keyword,
            sort=sort,
        )
    except (CoreException, HTTPException):
        # 정상적인 401, 403, 404 예외는 500으로 마스킹하지 않고 그대로 통과
        raise
    except Exception as e:
        print(f"❌ [AppRouter] Dynamic Loading Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
