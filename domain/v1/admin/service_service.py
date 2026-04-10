from sqlalchemy.orm import Session
from models import ServiceInstance, ServiceApp, ServiceEngine, ServiceRegistry
from typing import List, Dict, Any

def resolve_service_instance(db: Session, instance_id: int) -> List[Dict[str, Any]]:
    """
    [Bundle-Driven] 서비스 인스턴스(꾸러미)에 담긴 앱들을 순서대로 해석하여 
    프론트엔드용 명세(ResolvedServiceBinding) 리스트로 반환합니다.
    """
    instance = db.query(ServiceInstance).filter(ServiceInstance.id == instance_id).first()
    if not instance or not instance.service_app_ids:
        return []

    resolved_list = []
    # 번들에 등록된 앱 ID 리스트를 순회하며 정보 조립
    for app_id in instance.service_app_ids:
        app = db.query(ServiceApp).filter(ServiceApp.id == app_id).first()
        if not app or not app.is_active:
            continue
            
        # 엔진 정보를 가져와서 컴포넌트명 추출
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
