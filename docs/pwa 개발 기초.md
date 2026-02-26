# PWA (Progressive Web App) 개발 기초

이 문서는 이 프로젝트에 PWA를 직접 구현하면서 배운 개념과 코드를 상세히 기록한 가이드입니다. "왜?"에 집중하여 처음 접하는 사람도 이해할 수 있도록 작성되었습니다.

---

## 1. PWA란 무엇인가?

### 한 줄 정의
> **"브라우저로 만들었지만, OS가 앱처럼 취급해주는 웹사이트"**

### 일반 웹사이트와 PWA의 차이

| 기능 | 일반 웹사이트 | PWA |
|---|---|---|
| 홈 화면에 설치 | ❌ | ✅ |
| 앱처럼 전체화면 실행 | ❌ | ✅ |
| 앱이 꺼진 상태 푸시 알림 | ❌ | ✅ |
| 오프라인 동작 | ❌ | ✅ |
| 아이콘 배지 표시 | ❌ | ✅ |
| OS 공유 기능 연동 | ❌ | ✅ |

---

## 2. PWA의 3가지 필수 조건

브라우저(크롬, 사파리 등)가 웹사이트를 "앱으로 인정"하려면 **딱 3가지**가 필요합니다.

```
✅ 1. HTTPS (암호화된 안전한 도메인)
✅ 2. manifest.json (앱의 명세서)
✅ 3. Service Worker (백그라운드 담당자)
```

이 3가지를 갖추는 순간, 브라우저가 OS에게 이렇게 말합니다:
> "이 웹사이트는 신뢰할 수 있는 앱이야. 카메라, 알림, 오프라인 기능을 허용해줘."

---

## 3. 구현 내용 (이 프로젝트 기준)

### 3-1. HTTPS 확보 (이미 완료)

Cloudflare Tunnel을 통해 `https://jeju.live` 도메인이 연결되어 있으므로 자동 완료 상태입니다. HTTPS가 없으면 서비스 워커 자체가 등록 불가능하므로 가장 중요한 전제 조건입니다.

---

### 3-2. manifest.json (앱 명세서)

**파일 위치**: `svelte/static/manifest.json`

```json
{
  "name": "My Board App",
  "short_name": "Board",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#ffffff",
  "icons": [
    {
      "src": "/favicon.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ]
}
```

**각 항목 설명**

| 항목 | 설명 |
|---|---|
| `name` | 앱 설치 화면에 표시되는 전체 이름 |
| `short_name` | 홈 화면 아이콘 아래에 표시되는 짧은 이름 |
| `start_url` | 앱 아이콘을 눌렀을 때 처음 열리는 페이지 |
| `display: "standalone"` | 주소창 없이 앱처럼 전체화면으로 실행 |
| `theme_color` | 모바일 상단 상태바 색상 |
| `icons` | 홈 화면 아이콘 이미지 (192x192, 512x512 권장) |

**app.html 연결 (`svelte/src/app.html`)**

```html
<head>
    <link rel="manifest" href="%sveltekit.assets%/manifest.json" />
    <meta name="theme-color" content="#ffffff" />
</head>
```

---

### 3-3. Service Worker (백그라운드 담당자)

**파일 위치**: `svelte/static/sw.js`

```js
// 푸시 알림을 받으면 화면에 띄움
self.addEventListener('push', function(event) {
    const data = event.data ? event.data.text() : '새 알림이 도착했습니다.';
    event.waitUntil(
        self.registration.showNotification('jeju.live 알림', {
            body: data,
            icon: '/favicon.png'
        })
    );
});

// 알림 클릭 시 앱으로 포커스 이동
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            if (clientList.length > 0) return clientList[0].focus();
            return clients.openWindow('/');
        })
    );
});
```

**서비스 워커의 역할**

서비스 워커는 탭이 닫혀도 브라우저 백그라운드에 살아있는 "중간 담당자" 스크립트입니다.
- 브라우저와 서버 사이의 모든 네트워크 요청을 가로챌 수 있음
- 푸시 신호가 오면 알림을 대신 표시
- 오프라인 시 캐시된 콘텐츠를 대신 제공
- 백그라운드 동기화 처리

---

## 4. 웹 푸시 알림 (Web Push Notification)

PWA의 꽃이라고 할 수 있는 기능입니다. **앱이 꺼진 상태에서도 사용자에게 알림을 보낼 수 있습니다.**

### 4-1. 전체 작동 흐름

```
[사용자가 "알림 허용" 클릭]
       ↓
[브라우저가 구글/애플 서버에서 "구독 정보(endpoint)" 발급받음]
       ↓
[프론트엔드가 구독 정보를 백엔드(FastAPI)로 전송 → DB에 저장]
       ↓
[이벤트 발생 (새 댓글, 공지 등)]
       ↓
[백엔드가 DB에서 endpoint 꺼내서 구글/애플 푸시 서버로 POST 요청]
       ↓
[구글/애플 서버가 해당 기기 브라우저로 신호 전달]
       ↓
[서비스 워커(sw.js)가 깨어나 화면에 알림 팝업 표시] 🔔
```

### 4-2. VAPID 키란?

백엔드와 구글/애플 푸시 서버가 서로를 신뢰하기 위해 사용하는 암호 키 쌍입니다.

```
Public Key  → 프론트엔드에서 사용 (브라우저 구독 시 사용)
Private Key → 백엔드에서만 사용 (알림 발송 시 서명에 사용)
```

**생성 방법** (Svelte 컨테이너 내부에서):
```bash
docker compose exec svelte npx web-push generate-vapid-keys
```

**저장 위치**: `docker-compose.yml` 백엔드 서비스의 `environment` 블록

```yaml
- VAPID_PUBLIC_KEY=BFo_ZVq...
- VAPID_PRIVATE_KEY=4pEtY2A...
- VAPID_SUBJECT=mailto:admin@jeju.live
```

### 4-3. 알림 구독 기준

> **"이 기기의 이 브라우저에서 이 도메인에 대해 허용했는가?"**

| 조건 | 내용 |
|---|---|
| **기기별** | PC 크롬에서 허용해도 폰 크롬은 따로 허용 필요 |
| **브라우저별** | 크롬 허용 ≠ 엣지 허용 |
| **도메인별** | jeju.live의 허용은 다른 사이트와 무관 |
| **로그인 무관** | 비로그인 사용자도 구독 가능 |
| **세션 무관** | 세션 만료와 상관없이 구독 유지 |

### 4-4. 재부팅 후 동작

| 상황 | 결과 |
|---|---|
| 탭 닫기 | ✅ 알림 수신 가능 (크롬 백그라운드 살아있음) |
| 브라우저 최소화 | ✅ 알림 수신 가능 |
| PC/폰 재부팅 | ❌ 크롬을 한 번 실행해야 다시 알림 수신 시작 |
| 오프라인 상태 | 온라인 복귀 시 밀린 알림 일괄 수신 |

---

## 5. 백엔드 구현 (FastAPI)

**파일 위치**: `domain/push/push_router.py`

```python
from pywebpush import webpush, WebPushException

# 1. 구독 정보 저장 API
@router.post("/subscribe")
def subscribe(sub: SubscriptionRequest, db: Session = Depends(get_db)):
    existing = db.query(PushSubscription).filter(
        PushSubscription.endpoint == sub.endpoint
    ).first()
    if not existing:
        db.add(PushSubscription(
            endpoint=sub.endpoint,
            p256dh=sub.keys.p256dh,
            auth=sub.keys.auth
        ))
        db.commit()
    return {"message": "구독 완료"}

# 2. 전체 발송 API
@router.post("/send-all")
def send_all(db: Session = Depends(get_db)):
    subscriptions = db.query(PushSubscription).all()
    for sub in subscriptions:
        webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data="새 알림입니다!",
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT}
        )
```

**DB 모델** (`models.py`):
```python
class PushSubscription(Base):
    __tablename__ = "push_subscription"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    endpoint = Column(String, unique=True, nullable=False)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    user = relationship("User", backref="push_subscriptions")
```

---

## 6. Nginx 프록시 경로 주의사항

```nginx
location /api/ {
    proxy_pass http://backend:8000/;  # /api/가 /로 변환됨!
}
```

Nginx가 `/api/` 경로를 백엔드로 넘길 때 `/api/` 부분을 제거하므로, FastAPI 라우터의 prefix는 `/api` 없이 작성해야 합니다.

```python
# ❌ 잘못된 예
router = APIRouter(prefix="/api/push")

# ✅ 올바른 예
router = APIRouter(prefix="/push")
```

---

## 7. 앞으로 구현 가능한 PWA 기능들

### 단기 (바로 구현 가능)

**오프라인 페이지**
```js
// sw.js에 추가
self.addEventListener('fetch', function(event) {
    event.respondWith(
        fetch(event.request).catch(() => caches.match('/offline.html'))
    );
});
```

**공유 기능 (Web Share API)**
```js
await navigator.share({ title: '게시글 제목', url: window.location.href });
```

### 중기

- **배지(Badge) API**: 앱 아이콘에 읽지 않은 알림 숫자 표시
- **백그라운드 동기화**: 오프라인 상태에서 작성한 글을 온라인 복귀 시 자동 발송
- **유저별 알림**: 댓글 작성 시 게시글 작성자에게만 알림 발송

---

## 8. 도커 명령어 모음

```bash
# 백엔드 컨테이너에서 패키지 설치
docker compose exec backend uv add pywebpush

# Alembic 마이그레이션 (DB 테이블 변경사항 반영)
docker compose exec backend uv run alembic revision --autogenerate -m "add push subscription"
docker compose exec backend uv run alembic upgrade head

# VAPID 키 생성 (Svelte 컨테이너에서)
docker compose exec svelte npx web-push generate-vapid-keys

# 프론트엔드 이미지 재빌드 후 재시작
docker compose up -d --build frontend

# 백엔드 환경변수 변경 후 재시작 (빌드 불필요)
docker compose up -d --no-build backend
```

---

**작성일**: 2026년 2월 23일  
**작성자**: Antigravity (with User)  
**환경**: SvelteKit + FastAPI + Docker + Cloudflare Tunnel  
