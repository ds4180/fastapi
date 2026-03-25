// 서비스 워커: 백그라운드 푸시 알림 및 API 캐싱 제어
const CACHE_NAME = 'board-cache-v1';

// 푸시 알림 수신
self.addEventListener('push', function (event) {
    const data = event.data ? event.data.text() : '새 알림이 도착했습니다.';
    event.waitUntil(
        self.registration.showNotification('jeju.live 알림', {
            body: data,
            icon: '/favicon.png'
        })
    );
});

// 알림 클릭 시 앱으로 포커스 이동
self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            if (clientList.length > 0) {
                return clientList[0].focus();
            }
            return clients.openWindow('/');
        })
    );
});

// fetch 이벤트 핸들러: 네트워크 우선 전략 (API 요청 시)
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // ⛔ 에러 수정: url(객체)이 아닌 url.pathname(문자열)에서 startsWith를 호출해야 합니다.
    if (url.pathname.startsWith('/api')) {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    // 성공 시 네트워크 결과 반환
                    return response;
                })
                .catch(() => {
                    // 네트워크 실패 시 (오프라인 등) 캐시 시도 (필요 시 구현)
                    return caches.match(event.request);
                })
        );
    }
});
