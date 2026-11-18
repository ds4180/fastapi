from datetime import datetime
from sqlalchemy.orm import Session
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
    comments = db.query(Comment).filter(
        Comment.post_id == post_id,
        Comment.parent_id == None
    ).order_by(Comment.create_date.asc()).all()

    target_ids = _collect_comment_ids(comments)
    if target_ids:
        assets = db.query(MediaAsset).filter(
            MediaAsset.app_id == "comment",
            MediaAsset.target_id.in_(target_ids),
            MediaAsset.is_deleted == False
        ).order_by(MediaAsset.id.asc()).all()
        media_map = {}
        for asset in assets:
            media_map.setdefault(str(asset.target_id), []).append(_serialize_asset(asset))
        _attach_media_map(comments, media_map)
    return comments


def create_comment(db: Session, post_id: int, user_id: int, comment_in: CommentCreate):
    db_comment = Comment(
        post_id=post_id,
        user_id=user_id,
        content=comment_in.content,
        parent_id=comment_in.parent_id,
        create_date=datetime.now()
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

    linked_assets = db.query(MediaAsset).filter(
        MediaAsset.app_id == "comment",
        MediaAsset.target_id == str(db_comment.id),
        MediaAsset.is_deleted == False,
    ).all()
    for asset in linked_assets:
        media_service.delete_asset(db, asset.id)

    db.delete(db_comment)
    db.commit()
