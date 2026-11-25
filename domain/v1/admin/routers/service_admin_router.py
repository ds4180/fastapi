from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.deps import require_app_permission
from database import get_db
from domain.v1.admin import admin_schema
from models import ServiceApp, ServiceEngine, ServiceInstance, ServiceRegistry, User

router = APIRouter()

check_service_admin = require_app_permission("services", action="read")
check_service_admin_write = require_app_permission("services", action="write")


# 1. Service Registry (대분류)
@router.get("/service-registries", response_model=List[admin_schema.ServiceRegistrySchema])
def list_service_registries(db: Session = Depends(get_db), admin: User = Depends(check_service_admin)):
    return db.query(ServiceRegistry).all()


@router.post("/service-registries", response_model=admin_schema.ServiceRegistrySchema)
def create_service_registry(
    data: admin_schema.ServiceRegistryCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = ServiceRegistry(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put("/service-registries/{registry_id}", response_model=admin_schema.ServiceRegistrySchema)
def update_service_registry(
    registry_id: str,
    data: admin_schema.ServiceRegistryUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = db.query(ServiceRegistry).filter(ServiceRegistry.id == registry_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="레지스트리를 찾을 수 없습니다.")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(db_obj, k, v)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.delete("/service-registries/{registry_id}")
def delete_service_registry(
    registry_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = db.query(ServiceRegistry).filter(ServiceRegistry.id == registry_id).first()
    if not db_obj:
        raise HTTPException(status_code=404)
    db.delete(db_obj)
    db.commit()
    return {"message": "success"}


# 2. Service Engine (컴포넌트 버전)
@router.get("/service-engines", response_model=List[admin_schema.ServiceEngineSchema])
def list_service_engines(db: Session = Depends(get_db), admin: User = Depends(check_service_admin)):
    return db.query(ServiceEngine).all()


@router.post("/service-engines", response_model=admin_schema.ServiceEngineSchema)
def create_service_engine(
    data: admin_schema.ServiceEngineCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = ServiceEngine(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put("/service-engines/{engine_id}", response_model=admin_schema.ServiceEngineSchema)
def update_service_engine(
    engine_id: str,
    data: admin_schema.ServiceEngineUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = db.query(ServiceEngine).filter(ServiceEngine.id == engine_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="구현 엔진을 찾을 수 없습니다.")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(db_obj, k, v)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.delete("/service-engines/{engine_id}")
def delete_service_engine(
    engine_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = db.query(ServiceEngine).filter(ServiceEngine.id == engine_id).first()
    if not db_obj:
        raise HTTPException(status_code=404)
    db.delete(db_obj)
    db.commit()
    return {"message": "success"}


# 3. Service App (원자적 인스턴스)
@router.get("/service-apps", response_model=List[admin_schema.ServiceAppSchema])
def list_service_apps(db: Session = Depends(get_db), admin: User = Depends(check_service_admin)):
    return db.query(ServiceApp).all()


@router.post("/service-apps", response_model=admin_schema.ServiceAppSchema)
def create_service_app(
    data: admin_schema.ServiceAppCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = ServiceApp(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put("/service-apps/{app_id}", response_model=admin_schema.ServiceAppSchema)
def update_service_app(
    app_id: int,
    data: admin_schema.ServiceAppUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = db.query(ServiceApp).filter(ServiceApp.id == app_id).first()
    if not db_obj:
        raise HTTPException(status_code=404)
    for k, v in data.dict(exclude_unset=True).items():
        setattr(db_obj, k, v)
    db.commit()
    db.refresh(db_obj)
    return db_obj


# 4. Service Instance (번들)
@router.get("/service-instances", response_model=List[admin_schema.ServiceInstanceSchema])
def list_service_instances(db: Session = Depends(get_db), admin: User = Depends(check_service_admin)):
    return db.query(ServiceInstance).all()


@router.post("/service-instances", response_model=admin_schema.ServiceInstanceSchema)
def create_service_instance(
    data: admin_schema.ServiceInstanceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = ServiceInstance(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put("/service-instances/{instance_id}", response_model=admin_schema.ServiceInstanceSchema)
def update_service_instance(
    instance_id: int,
    data: admin_schema.ServiceInstanceUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    from sqlalchemy.orm.attributes import flag_modified

    db_obj = db.query(ServiceInstance).filter(ServiceInstance.id == instance_id).first()
    if not db_obj:
        raise HTTPException(status_code=404)
    update_fields = data.model_dump(exclude_unset=True)
    for k, v in update_fields.items():
        setattr(db_obj, k, v)
        if k == "service_app_ids":
            flag_modified(db_obj, "service_app_ids")
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.delete("/service-instances/{instance_id}")
def delete_service_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_service_admin_write),
):
    db_obj = db.query(ServiceInstance).filter(ServiceInstance.id == instance_id).first()
    if not db_obj:
        raise HTTPException(status_code=404)
    db.delete(db_obj)
    db.commit()
    return {"message": "success"}
