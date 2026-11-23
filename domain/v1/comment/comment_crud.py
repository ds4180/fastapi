from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value
from models import Comment, User, MediaAsset
from domain.v1.comment.comment_schema import CommentCreate, CommentUpdate


def _serialize_asset(asset: MediaAsset) -> dict:
    return {
        "id": asset.id,
        "original_name": asset.original_name,
        "mime_type": asset.mime_type,
        "file_size": asset.file_size,
        "file_path": asset.file_path,
        "category": asset.category,
        "access_level": asset.access_level,
        "meta_info": asset.meta_info or {},
    }


def _collect_comment_ids(comments: list) -> list:
    ids = []
    for c in comments:
        ids.append(str(c.id))
        if getattr(c, "sub_comments", None):
            ids.extend(_collect_comment_ids(c.sub_comments))
    return ids


def _attach_media_map(comments: list, media_map: dict):
    for c in comments:
        setattr(c, "attachments", media_map.get(str(c.id), []))
        if getattr(c, "sub_comments", None):
            _attach_media_map(c.sub_comments, media_map)


def get_comments_by_post(db: Session, post_id: int):
    """특정 게시물의 댓글 목록을 1회 쿼리로 조회하여 2단계 트리(N+1 방지)로 조립합니다."""
    all_comments = (
        db.query(Comment)
        .filter(Comment.post_id == post_id)
        .order_by(Comment.create_date.asc(), Comment.id.asc())
        .all()
    )
    if not all_comments:
        return []

    target_ids = [str(c.id) for c in all_comments]
    assets = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.app_id == "comment",
            MediaAsset.target_id.in_(target_ids),
            MediaAsset.is_deleted == False,
        )
        .order_by(MediaAsset.id.asc())
        .all()
    )
    media_map: dict[str, list] = {}
    for asset in assets:
        media_map.setdefault(str(asset.target_id), []).append(_serialize_asset(asset))

    children_map: dict[int, list[Comment]] = {}
    roots: list[Comment] = []
    for c in all_comments:
        setattr(c, "attachments", media_map.get(str(c.id), []))
        set_committed_value(c, "sub_comments", [])
        if c.parent_id is None:
            roots.append(c)
        else:
            children_map.setdefault(c.parent_id, []).append(c)

    for root in roots:
        set_committed_value(root, "sub_comments", children_map.get(root.id, []))

    return roots


def create_comment(db: Session, post_id: int, user_id: int, comment_in: CommentCreate):
    resolved_parent_id = comment_in.parent_id
    if resolved_parent_id is not None:
        parent = (
            db.query(Comment)
            .filter(Comment.id == resolved_parent_id, Comment.post_id == post_id)
            .first()
        )
        if not parent:
            raise HTTPException(status_code=400, detail="유효하지 않은 부모 댓글입니다.")
        # 2단계 고정: 2단 답글에 달린 답글도 최상위 원댓글 하위에 연결
        if parent.parent_id is not None:
            resolved_parent_id = parent.parent_id

    db_comment = Comment(
        post_id=post_id,
        user_id=user_id,
        content=comment_in.content,
        parent_id=resolved_parent_id,
        create_date=datetime.now(),
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    attachments = []
    if comment_in.media_ids:
        db.query(MediaAsset).filter(
            MediaAsset.id.in_(comment_in.media_ids),
            MediaAsset.user_id == user_id
        ).update({
            "app_id": "comment",
            "target_id": str(db_comment.id)
        }, synchronize_session=False)
        db.commit()
        linked_assets = db.query(MediaAsset).filter(
            MediaAsset.app_id == "comment",
            MediaAsset.target_id == str(db_comment.id),
            MediaAsset.is_deleted == False
        ).order_by(MediaAsset.id.asc()).all()
        attachments = [_serialize_asset(a) for a in linked_assets]

    setattr(db_comment, "attachments", attachments)
    return db_comment

def update_comment(db: Session, db_comment: Comment, comment_in: CommentUpdate):
    from domain.media import media_service

    db_comment.content = comment_in.content
    db_comment.modify_date = datetime.now()

    if comment_in.remove_media_ids:
        remove_assets = db.query(MediaAsset).filter(
            MediaAsset.id.in_(comment_in.remove_media_ids),
            MediaAsset.app_id == "comment",
            MediaAsset.target_id == str(db_comment.id),
            MediaAsset.is_deleted == False,
        ).all()
        for asset in remove_assets:
            media_service.delete_asset(db, asset.id)

    if comment_in.media_ids:
        db.query(MediaAsset).filter(
            MediaAsset.id.in_(comment_in.media_ids),
            MediaAsset.user_id == db_comment.user_id,
        ).update({
            "app_id": "comment",
            "target_id": str(db_comment.id),
        }, synchronize_session=False)

    db.commit()
    db.refresh(db_comment)
    linked_assets = db.query(MediaAsset).filter(
        MediaAsset.app_id == "comment",
        MediaAsset.target_id == str(db_comment.id),
        MediaAsset.is_deleted == False,
    ).order_by(MediaAsset.id.asc()).all()
    setattr(db_comment, "attachments", [_serialize_asset(a) for a in linked_assets])
    return db_comment

def delete_comment(db: Session, db_comment: Comment):
    from domain.media import media_service

    target_ids = _collect_comment_ids([db_comment])
    if target_ids:
        linked_assets = db.query(MediaAsset).filter(
            MediaAsset.app_id == "comment",
            MediaAsset.target_id.in_(target_ids),
            MediaAsset.is_deleted == False,
        ).all()
        for asset in linked_assets:
            media_service.delete_asset(db, asset.id)

    db.delete(db_comment)
    db.commit()
