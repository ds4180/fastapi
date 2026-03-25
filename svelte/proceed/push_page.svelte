<script>
    import { invalidateAll } from "$app/navigation";

    /** @type {import('./$types').PageData} */
    let { data } = $props();

    // VAPID 공개키 (백엔드 환경변수와 동일한 키)
    const VAPID_PUBLIC_KEY =
        "BFo_ZVqvUj1h1Z-wRRsHn9-uJecPXcPqGnDNfEuy6-H16ax9-H_-JTyAH_9gEyLQTD_yxv5dB3cupfG2SCSk62A";

    // 1. [알림 구독하기] 버튼 클릭 시 동작
    async function subscribeToPush() {
        if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
            alert("이 브라우저는 푸시 알림을 지원하지 않습니다.");
            return;
        }

        try {
            // 알림 권한 요청
            const permission = await Notification.requestPermission();
            if (permission !== "granted") {
                alert("알림 권한이 거부되었습니다.");
                return;
            }

            // 서비스 워커 등록 및 준비 대기
            const reg = await navigator.serviceWorker.register("/sw.js");
            await navigator.serviceWorker.ready;

            // 브라우저에서 구독 정보(Subscription) 생성
            const subscription = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: VAPID_PUBLIC_KEY,
            });

            // 백엔드 API로 구독 정보 전송 (저장)
            const res = await fetch("/api/push/subscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(subscription),
            });

            if (res.ok) {
                alert(
                    "✅ 알림 구독 완료! 이제 백그라운드에서도 알림을 받을 수 있습니다.",
                );
            } else {
                alert(
                    "❌ 구독 저장 중 오류가 발생했습니다. 콘솔을 확인해 주세요.",
                );
            }
        } catch (error) {
            console.error("푸시 구독 오류:", error);
            alert(`오류 발생: ${error.message}`);
        }
    }

    // 2. [모두에게 알림 쏘기] 버튼 클릭 시 동작
    async function testPushAll() {
        try {
            const res = await fetch("/api/push/send-all", { method: "POST" });
            const result = await res.json();
            alert(`📤 전송 완료! ${result.sent}명에게 알림을 보냈습니다.`);
        } catch (error) {
            console.error("알림 전송 오류:", error);
            alert(`오류 발생: ${error.message}`);
        }
    }
</script>

<button onclick={() => invalidateAll()}>새로고침</button>
<br /><br />

<!-- 추가되는 푸시 알림 테스트 버튼 2개 -->
<div
    style="border: 1px solid #ccc; padding: 15px; border-radius: 8px; margin-bottom: 20px;"
>
    <h3>🔔 푸시 알림 테스트</h3>
    <button
        onclick={subscribeToPush}
        style="margin-right: 10px; padding: 8px 15px;"
        >1. 알림 수신 허용하기 (구독)</button
    >
    <button
        onclick={testPushAll}
        style="padding: 8px 15px; background-color: #ffeb3b; color: black; border: 1px solid #ccc;"
        >2. (관리자용) 가입자 모두에게 알림 쏘기!</button
    >
</div>

{#if data.username}<p>안녕하세요, {data.username}님!</p>{/if}
docker 연결 성공 <br />
CF 도메인 보안 등록 성공
