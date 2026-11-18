from sqlalchemy.orm import Session
from models import ServiceInstance, ServiceApp, ServiceEngine, ServiceRegistry
from typing import List, Dict, Any

def resolve_service_apps(db: Session, service_app_ids: List[int]) -> List[Dict[str, Any]]:
    """
    [App-Driven] 서비스 앱 ID 리스트를 순서대로 해석하여
    프론트엔드용 명세(ResolvedServiceBinding) 리스트로 반환합니다.
    """
    if not service_app_ids:
        return []

    resolved_list = []
    for app_id in service_app_ids:
        app = db.query(ServiceApp).filter(ServiceApp.id == app_id).first()
        if not app or not app.is_active:
            continue

        engine = db.query(ServiceEngine).filter(ServiceEngine.id == app.engine_id).first()
        if not engine:
            continue

        resolved_list.append({
            "service_id": engine.registry_id,
            "engine_id": engine.id,
            "service_component": engine.frontend_plugin,
            "config": app.config
        })

    return resolved_list


def resolve_service_instance(db: Session, instance_id: int) -> List[Dict[str, Any]]:
    """
    [Bundle-Driven] 서비스 인스턴스(꾸러미)에 담긴 앱들을 순서대로 해석하여 
    프론트엔드용 명세(ResolvedServiceBinding) 리스트로 반환합니다.
    """
    instance = db.query(ServiceInstance).filter(ServiceInstance.id == instance_id).first()
    if not instance or not instance.service_app_ids:
        return []
    return resolve_service_apps(db, instance.service_app_ids)


def resolve_board_services(db: Session, board: Any) -> List[Dict[str, Any]]:
    """
    [Board-Driven] 게시판에 직접 지정된 service_app_ids가 있으면 우선 적용하고,
    없으면 연결된 공통 번들(service_instance_id)을 해석합니다.
    """
    direct_ids = getattr(board, "service_app_ids", None) or []
    if direct_ids:
        return resolve_service_apps(db, direct_ids)
    instance_id = getattr(board, "service_instance_id", None)
    if instance_id:
        return resolve_service_instance(db, instance_id)
    return []
