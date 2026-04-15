from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from domain.user.user_router import get_current_user
from domain.media import media_service
from models import User

router = APIRouter(
    prefix="/media",
    tags=["Media System"]
)

@router.post("/upload")
async def media_upload(
    files: List[UploadFile] = File(...),
    app_id: str = "general",
    target_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [미디어 통합 업로드 API]
    - 인증된 사용자만 업로드 가능
    - MediaAsset 모델 기반 DB 자동 등록 및 물리 파일 격리 저장
    """
    try:
        assets = await media_service.media_process_upload(
            db=db,
            user=current_user,
            files=files,
            app_id=app_id,
            target_id=target_id
        )
        return assets
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def media_list(
    app_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """사용자 본인이 올린 미디어 자산 목록 조회 (탐색기 기초 데이터)"""
    from models import MediaAsset
    query = db.query(MediaAsset).filter(MediaAsset.user_id == current_user.id, MediaAsset.is_deleted == False)
    if app_id:
        query = query.filter(MediaAsset.app_id == app_id)
    
    return query.order_by(MediaAsset.created_at.desc()).all()

@router.get("/admin/stats")
async def media_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[전체 관리자] 시스템 미디어 통합 통계 및 계층별 요약"""
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    from sqlalchemy import func
    from models import MediaAsset
    import os
    from domain.media import media_config
    
    # 1. DB 기반 통계
    total_count = db.query(MediaAsset).filter(MediaAsset.is_deleted == False).count()
    total_size = db.query(func.sum(MediaAsset.file_size)).filter(MediaAsset.is_deleted == False).scalar() or 0
    
    # 2. 계층별 상세 통계
    tier_stats = db.query(
        MediaAsset.access_level,
        func.count(MediaAsset.id),
        func.sum(MediaAsset.file_size)
    ).filter(MediaAsset.is_deleted == False).group_by(MediaAsset.access_level).all()
    
    tier_summary = {
        row[0]: {"count": row[1], "size": row[2] or 0} for row in tier_stats
    }
    
    # 3. 물리 폴더 스캔 (대시보드 요약용)
    folder_summary = {}
    for tier in ['public', 'protected', 'private', 'system', 'tmp']:
        tier_path = os.path.join(media_config.MEDIA_ROOT, tier)
        size = 0
        count = 0
        if os.path.exists(tier_path):
            for dirpath, dirnames, filenames in os.walk(tier_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    size += os.path.getsize(fp)
                    count += 1
        folder_summary[tier] = {"size": size, "count": count}

    return {
        "total_count": total_count,
        "total_size_bytes": total_size,
        "tier_summary": tier_summary,
        "folder_physical_summary": folder_summary
    }

@router.get("/admin/all")
async def media_admin_all(
    page: int = 1,
    size: int = 24,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[전체 관리자] 전역 미디어 자산 목록 탐색 (Windows급 탐색기 데이터)"""
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    from models import MediaAsset
    offset = (page - 1) * size
    
    query = db.query(MediaAsset).filter(MediaAsset.is_deleted == False)
    total = query.count()
    items = query.order_by(MediaAsset.created_at.desc()).offset(offset).limit(size).all()
    
    return {
        "total": total,
        "items": items,
        "page": page,
        "size": size
    }

@router.delete("/delete/{asset_id}")
async def media_delete(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """미디어 자산 삭제 (소프트 삭제 및 물리 격리)"""
    # 랭크 4 관리자거나 소유자여야 함 (로직은 서비스에서 처리하거나 여기서 체크)
    success = media_service.delete_asset(db, asset_id)
    if not success:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없거나 삭제에 실패했습니다.")
    return {"message": "Successfully deleted"}
