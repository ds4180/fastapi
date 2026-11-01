"""
============================================================================
[테스트 5: 통합 감사로그(AuditLog) 및 실사용 관제 인프라 검사 (tests/test_audit.py)]
============================================================================

💡 이 테스트의 목적:
[Phase 2 - 1단계] 감사로그 기반 인프라가 실사용에 충분하도록 견고하게 동작하는지 검증합니다:
1. audit_logs 테이블이 Base 메타데이터에 등록되었는가
2. 개인정보/비밀번호 마스킹(sanitize_diff)이 빈틈없이 작동하는가
3. 사용자 신분 스냅샷(get_user_summary)이 정확하게 생성되는가
4. AuditLog 레코드가 정상적으로 인스턴스화되고 속성을 유지하는가
"""

from models import Base, User, UserProfile, AuditLog
from core.audit import sanitize_diff, get_user_summary


def test_audit_model_metadata():
    """
    [검사 1] audit_logs 테이블이 SQLAlchemy 메타데이터에 정상 등록되었는가?
    """
    tables = Base.metadata.tables
    assert "audit_logs" in tables, "audit_logs 테이블이 Base 메타데이터에 누락되었습니다."

    table = tables["audit_logs"]
    columns = [c.name for c in table.columns]
    
    # 핵심 컬럼 존재 검증
    expected_cols = [
        "id", "app_id", "log_type", "severity", "action",
        "user_id", "user_summary", "resource_type", "resource_id",
        "title", "message", "diff_payload", "metadata", "ip_address", "created_at"
    ]
    for col in expected_cols:
        assert col in columns, f"필수 컬럼 '{col}'이 audit_logs 테이블에 없습니다."


def test_sanitize_diff_privacy_masking():
    """
    [검사 2 - 실사용 방어벽] 비밀번호, 주민등록번호, 계좌번호 등 민감 정보가
    diff_payload에서 '********'로 완벽하게 마스킹되는가?
    """
    sample_diff = [
        {"field": "driver_name", "from": "김철수", "to": "이영희"},
        {"field": "password", "from": "plain_secret_1234", "to": "new_secret_5678"},
        {"field": "resident_no", "from": "900101-1234567", "to": "900101-2345678"},
        {"field": "account_no", "from": "110-123-456789", "to": "110-987-654321"},
        {"field": "bus_number", "from": "제주79자 1001", "to": "제주79자 1005"},
    ]

    safe_diff = sanitize_diff(sample_diff)

    # 1. 일반 필드는 원래 값 보존
    assert safe_diff[0]["from"] == "김철수"
    assert safe_diff[0]["to"] == "이영희"
    assert safe_diff[4]["from"] == "제주79자 1001"
    assert safe_diff[4]["to"] == "제주79자 1005"

    # 2. 민감 필드는 모두 '********'로 마스킹
    assert safe_diff[1]["from"] == "********"
    assert safe_diff[1]["to"] == "********"
    assert safe_diff[2]["from"] == "********"
    assert safe_diff[2]["to"] == "********"
    assert safe_diff[3]["from"] == "********"
    assert safe_diff[3]["to"] == "********"


def test_user_summary_snapshot():
    """
    [검사 3] 사용자의 이름, 소속 부서, 랭크 레벨이 단일 스냅샷 문자열로 정확히 결합되는가?
    """
    # 1. 일반 로그인 사원
    user = User(username="driver_hong", real_name="홍길동", email="hong@jeju.live")
    user.profile = UserProfile(rank_level=2, primary_group="운수1팀")
    summary = get_user_summary(user)
    assert summary == "홍길동 (운수1팀/Lv.2)"

    # 2. 프로필 주그룹이 없는 사원
    user_no_group = User(username="newbie", real_name="신규사원", email="new@jeju.live")
    user_no_group.profile = UserProfile(rank_level=1, primary_group=None)
    assert get_user_summary(user_no_group) == "신규사원 (소속없음/Lv.1)"

    # 3. 비로그인 GUEST
    assert get_user_summary(None) == "GUEST (비로그인)"


def test_audit_log_instance_creation():
    """
    [검사 4] AuditLog 인스턴스가 올바른 타입과 기본값으로 생성되는가?
    """
    log = AuditLog(
        app_id="dispatch",
        log_type="CHANGE",
        severity="INFO",
        action="UPDATE",
        title="배차표 #42번 승무사원 변경",
        user_id=1,
        user_summary="홍길동 (운수1팀/Lv.2)",
        resource_type="dispatch",
        resource_id="42",
        diff_payload=[{"field": "driver", "from": "A", "to": "B"}],
        metadata_payload={"ip": "127.0.0.1"},
        ip_address="127.0.0.1",
    )

    assert log.app_id == "dispatch"
    assert log.log_type == "CHANGE"
    assert log.severity == "INFO"
    assert log.title == "배차표 #42번 승무사원 변경"
    assert len(log.diff_payload) == 1
    assert log.diff_payload[0]["field"] == "driver"


def test_request_id_middleware_and_header():
    """
    [검사 5 - 2단계 미들웨어 검증]
    모든 HTTP 응답에 X-Request-ID 및 X-Response-Time 헤더가 발급되는가?
    """
    from starlette.testclient import TestClient
    from main import app

    client = TestClient(app)
    
    # 1. 헤더 없이 호출 시 신규 req_ 식별자 자동 발급
    res1 = client.get("/hello")
    assert res1.status_code == 200
    assert "x-request-id" in res1.headers
    assert res1.headers["x-request-id"].startswith("req_")
    assert "x-response-time" in res1.headers

    # 2. 클라이언트가 특정 ID를 보냈을 때 그대로 재사용
    res2 = client.get("/hello", headers={"X-Request-ID": "custom_trace_999"})
    assert res2.status_code == 200
    assert res2.headers["x-request-id"] == "custom_trace_999"


def test_core_exception_handler_header():
    """
    [검사 6 - 2단계 예외 핸들러 검증]
    CoreException(403, 404 등) 발생 시에도 X-Request-ID 헤더가 누락 없이 반환되는가?
    """
    from starlette.testclient import TestClient
    from main import app

    client = TestClient(app)
    
    # 없는 페이지 또는 404 에러 라우트 호출 (표준 Envelope 검증)
    res = client.get("/api/v1/not-exists-page-test-endpoint-404")
    assert "x-request-id" in res.headers


def test_audit_mixin_and_diff_extraction():
    """
    [검사 7 - 3단계 AuditMixin 자동 Diff 캡처 검증]
    AuditMixin을 상속받은 모델의 필드를 수정했을 때,
    SQLAlchemy session.flush() 시점에 컬럼의 변경 전(from)과 변경 후(to) 차이점이
    100% 자동으로 감지되어 AuditLog로 생성되는가?
    """
    from sqlalchemy import Column, Integer, String, create_engine
    from sqlalchemy.orm import sessionmaker
    from models.base import Base, AuditMixin
    from models.audit import AuditLog

    class DummyResource(Base, AuditMixin):
        __tablename__ = "dummy_audit_test_res"
        __audit_app_id__ = "test_app"
        id = Column(Integer, primary_key=True)
        title = Column(String(50), default="초기제목")
        driver_name = Column(String(50), default="김기사")

    # 인메모리 SQLite에 테스트 테이블 생성
    engine = create_engine("sqlite:///:memory:")
    DummyResource.__table__.create(engine)
    AuditLog.__table__.create(engine)

    TestSession = sessionmaker(bind=engine)
    session = TestSession()

    # 1. 초기 데이터 생성 및 커밋
    res_obj = DummyResource(id=101, title="초기제목", driver_name="김기사")
    session.add(res_obj)
    session.commit()
    assert res_obj.version == 1

    # 2. 필드 수정 후 flush 수행 -> 리스너 자동 발동
    res_obj.title = "수정된제목"
    res_obj.driver_name = "박기사"
    session.flush()

    # 3. 버전 번호가 1에서 2로 자동 증가했는가?
    assert res_obj.version == 2

    # 4. 세션에 AuditLog가 자동 생성되어 탑재되었는가?
    session.commit()
    audit_entry = session.query(AuditLog).filter_by(app_id="test_app", resource_id="101").first()
    assert audit_entry is not None
    assert audit_entry.action == "UPDATE"
    assert audit_entry.resource_type == "dummy_audit_test_res"

    # 5. 변경 전/후 Diff 필드가 정확히 캡처되었는가?
    diff_fields = {d["field"]: (d["from"], d["to"]) for d in audit_entry.diff_payload}
    assert "title" in diff_fields
    assert diff_fields["title"] == ("초기제목", "수정된제목")
    assert "driver_name" in diff_fields
    assert diff_fields["driver_name"] == ("김기사", "박기사")

