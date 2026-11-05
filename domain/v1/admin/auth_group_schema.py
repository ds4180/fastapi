"""
============================================================================
[조직·권한 그룹 관제 Pydantic 스키마 (domain/v1/admin/auth_group_schema.py)]
============================================================================

3대 뷰 (그룹 뷰 / 사용자 뷰 / 앱 뷰) 데이터 전송 규격(DTO)을 정의합니다.
"""

from datetime import datetime
from typing import Optional, List, Union, Dict, Any
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# 📂 1. 그룹 뷰 (Group View) 스키마
# --------------------------------------------------------------------------

class GroupCreateReq(BaseModel):
    """신규 공식 그룹 생성 요청 (오직 root만 수행 가능)"""
    code: str = Field(..., min_length=1, max_length=50, description="그룹 고유 식별 코드 (예: '운수1팀', '배차담당')")
    name: str = Field(..., min_length=1, max_length=100, description="화면 표시용 그룹 이름")
    group_type: str = Field(default="PRIMARY", description="'PRIMARY'(주그룹/본소속) | 'SECONDARY'(부그룹/직무·특권)")
    category: str = Field(default="GENERAL", description="'GENERAL'(일반) | 'PRIVILEGE'(특권/Allow용) | 'RESTRICTION'(제재/Deny용)")
    description: Optional[str] = Field(default=None, description="그룹 설명 및 용도")


class GroupUpdateReq(BaseModel):
    """그룹 정보 수정 요청 (오직 root만 수행 가능)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    category: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)


class GroupItemRes(BaseModel):
    """그룹 목록 조회 응답 (소속 회원 수 및 앱 연동 현황 포함)"""
    id: int
    code: str
    name: str
    group_type: str
    category: str
    description: Optional[str]
    created_at: datetime
    primary_count: int = 0
    secondary_count: int = 0
    allow_apps: List[str] = []
    deny_apps: List[str] = []

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------
# 👤 2. 사용자 뷰 (User View) 스키마
# --------------------------------------------------------------------------

class UserGroupItemRes(BaseModel):
    """사용자 그룹 매칭 현황 응답"""
    id: int
    username: str
    real_name: Optional[str]
    email: str
    rank_level: int
    primary_group: Optional[str]
    secondary_groups: List[str] = []

    class Config:
        from_attributes = True


class UserPrimaryGroupReq(BaseModel):
    """사용자 주그룹 단일 설정 요청 (1인당 최대 1개)"""
    primary_group: Optional[str] = Field(default=None, description="설정할 주그룹 코드 (null/빈값일 경우 미지정 해제)")


class UserSecondaryGroupReq(BaseModel):
    """사용자 부그룹 단일 추가 요청"""
    code: str = Field(..., min_length=1, max_length=50, description="추가할 부그룹 코드")


class UserGroupBatchReq(BaseModel):
    """사용자 주/부그룹 일괄 설정 요청"""
    primary_group: Optional[str] = Field(default=None)
    secondary_groups: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# 📱 3. 앱 뷰 (App View) 스키마
# --------------------------------------------------------------------------

class AppPermissionItemRes(BaseModel):
    """앱 권한 설정 현황 응답"""
    app_id: str
    name: str
    title: Optional[str]
    description: Optional[str]
    app_type: str
    min_read_rank: int
    min_write_rank: int
    allow_groups: Union[List[str], Dict[str, Any], Any] = Field(default_factory=list)
    deny_groups: Union[List[str], Dict[str, Any], Any] = Field(default_factory=list)

    class Config:
        from_attributes = True


class AppPermissionsUpdateReq(BaseModel):
    """앱 권한 랭킹 및 allow/deny 설정 변경 요청 (오직 root만 수행 가능)"""
    min_read_rank: Optional[int] = Field(default=None, ge=0, le=9)
    min_write_rank: Optional[int] = Field(default=None, ge=0, le=9)
    allow_groups: Optional[Union[List[str], Dict[str, Any], Any]] = Field(default=None, description="허용 그룹 (단순 배열 또는 {read:[], write:[]} 객체)")
    deny_groups: Optional[Union[List[str], Dict[str, Any], Any]] = Field(default=None, description="차단 그룹 (단순 배열 또는 {read:[], write:[]} 객체)")


# --------------------------------------------------------------------------
# 🧩 4. 통합 인스턴스 뷰 (Instance View) 스키마 (게시판/페이지/커스텀앱 인스턴스)
# --------------------------------------------------------------------------

class InstancePermissionItemRes(BaseModel):
    """개별 인스턴스 단위 권한 설정 응답"""
    target_id: str = Field(..., description="인스턴스 고유 식별자 (예: '1', 'notice', 'dayoff')")
    instance_type: str = Field(..., description="'BOARD' | 'PAGE' | 'APP'")
    app_type: Optional[str] = Field(default="CUSTOM", description="3대 앱 분류: 'SYSTEM' | 'CUSTOM' | 'INSTANCE'")
    title: str = Field(..., description="인스턴스 화면 명칭 (예: '공지게시판', '결근계 관리')")
    slug: Optional[str] = Field(default=None, description="URL 슬러그")
    frontend_route: Optional[str] = Field(default=None, description="프론트엔드 실제 진입 라우트 주소")
    parent_engine: str = Field(..., description="상위 앱 엔진 명칭 (예: '게시판 (board)', '페이지 (page)', '단일 앱')")
    icon: Optional[str] = Field(default="mdi:apps", description="아이콘")
    min_read_rank: int = Field(default=0, ge=0, le=9)
    min_write_rank: int = Field(default=2, ge=0, le=9)
    allow_groups: Union[List[str], Dict[str, Any], Any] = Field(default_factory=list)
    deny_groups: Union[List[str], Dict[str, Any], Any] = Field(default_factory=list)


class InstancePermissionUpdateReq(BaseModel):
    """인스턴스 권한 랭킹 및 allow/deny 설정 변경 요청"""
    min_read_rank: Optional[int] = Field(default=None, ge=0, le=9)
    min_write_rank: Optional[int] = Field(default=None, ge=0, le=9)
    allow_groups: Optional[Union[List[str], Dict[str, Any], Any]] = Field(default=None, description="허용 그룹 (단순 배열 또는 {read:[], write:[]} 객체)")
    deny_groups: Optional[Union[List[str], Dict[str, Any], Any]] = Field(default=None, description="차단 그룹 (단순 배열 또는 {read:[], write:[]} 객체)")

