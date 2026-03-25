<script>
    /**
     * @file Alert.svelte
     * @description 프로젝트 전역 알림 컴포넌트 (중복 노출 방지 로직 보강)
     */
    import {
        notify,
        alerts,
        dismissedIds,
        sessionHiddenIds,
        isQuietMode,
    } from "$lib/store";
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import { fly, fade, slide } from "svelte/transition";
    import { onMount, onDestroy } from "svelte";

    /** @type { { positionFilter: 'top' | 'bottom' | 'modal' } } */
    let { positionFilter } = $props();
    let interval;

    async function fetchActiveAlerts() {
        try {
            const response = await fetch("/api/api/alert/active");
            if (response.ok) {
                const json = await response.json();
                if (JSON.stringify(json) !== JSON.stringify($alerts)) {
                    alerts.set(json);
                }
            }
        } catch (e) {
            console.warn("[Alert] 실시간 갱신 실패", e);
        }
    }

    onMount(() => {
        if (positionFilter === "modal") {
            fetchActiveAlerts();
            interval = setInterval(fetchActiveAlerts, 30000);
        }
    });

    onDestroy(() => {
        if (interval) clearInterval(interval);
    });

    // 🕒 날짜, 영구 삭제, 그리고 '세션 숨김' 기반 필터링
    let displayAlerts = $derived(
        ($alerts || []).filter((a) => {
            const now = new Date();

            // 1. 기간 체크
            if (a.start_date && new Date(a.start_date) > now) return false;
            if (a.end_date && new Date(a.end_date) < now) return false;

            // 2. 영구 삭제 체크 (LocalStorage)
            if ($dismissedIds[a.id]) return false;

            // 3. 💡 이번 세션 숨김 체크
            if ($sessionHiddenIds.has(a.id)) return false;

            // 4. 🤫 Quiet Mode (방해 금지) 체크
            if ($isQuietMode && a.level < 4) return false;

            const currentPath = $page.url.pathname;
            if (currentPath === "/alert-manage") return false;

            const pathMatch =
                !a.route ||
                a.route.trim() === "" ||
                a.route === "*" ||
                a.route
                    .split(",")
                    .map((r) => r.trim())
                    .includes(currentPath);
            if (!pathMatch) return false;

            if (positionFilter === "modal") return a.level >= 3;
            const pos = a.position || "top";
            return a.level < 3 && pos === positionFilter;
        }),
    );

    // 자동 소멸 (Level 1: 10초) - 이제 notify.dismiss()가 sessionHiddenIds를 업데이트하므로 안전함
    $effect(() => {
        ($alerts || []).forEach((alert) => {
            if (alert.level === 1 && !alert.timerStarted) {
                alert.timerStarted = true;
                setTimeout(() => notify.dismiss(alert.id), 10000);
            }
        });
    });

    let timers = $state({});
    let intervals = {};
    let penaltyMsg = $state({});

    function initTimer(node, alert) {
        if (
            (alert.level === 4 || alert.level === 5) &&
            timers[alert.id] === undefined
        ) {
            timers[alert.id] = alert.reset_sec || 5;
            const interval = setInterval(() => {
                if (timers[alert.id] > 0) {
                    timers[alert.id] -= 1;
                } else {
                    clearInterval(interval);
                    delete intervals[alert.id];
                }
            }, 1000);
            intervals[alert.id] = interval;
        }
        return {
            destroy() {
                if (intervals[alert.id]) {
                    clearInterval(intervals[alert.id]);
                }
            },
        };
    }

    function neverShowAgain(alertId) {
        dismissedIds.update((all) => {
            all[alertId] = true;
            return { ...all };
        });
        notify.dismiss(alertId); // 세션 숨김과 큐 삭제 동시 진행
    }

    async function handleConfirm(alert) {
        if ((alert.level === 4 || alert.level === 5) && timers[alert.id] > 0) {
            timers[alert.id] = alert.reset_sec || 5;
            penaltyMsg[alert.id] = "지시 사항을 정독하십시오! 🖐️";
            setTimeout(() => {
                penaltyMsg[alert.id] = null;
            }, 1500);
            return;
        }
        notify.dismiss(alert.id);
        if (alert.redirect_url) goto(alert.redirect_url);
    }

    function getCreatedTimeStr(dateStr) {
        if (!dateStr) return "";
        const date = new Date(dateStr);
        return date.toLocaleString("ko-KR", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        });
    }
</script>

{#each displayAlerts as alert (alert.id)}
    {#if alert.level === 5}
        <!-- 🚨 Level 5: 비상 전체 화면 -->
        <div class="emergency-overlay" transition:fade>
            <div
                class="emergency-container"
                use:initTimer={alert}
                transition:fly={{ scale: 1.1 }}
            >
                <div class="emergency-header">
                    <span class="pulse-text"
                        >🚨 긴급 알림 - {getCreatedTimeStr(
                            alert.create_date,
                        )}</span
                    >
                </div>
                <div class="emergency-body">
                    <div class="message-box">
                        <h1 class="message-text">{alert.message}</h1>
                    </div>
                </div>
                <div class="emergency-footer">
                    <button
                        class="btn btn-primary-emergency"
                        onclick={() => handleConfirm(alert)}
                    >
                        {#if penaltyMsg[alert.id]}
                            <span transition:fade>{penaltyMsg[alert.id]}</span>
                        {:else if timers[alert.id] > 0}
                            <span>{timers[alert.id]}초 정독 중...</span>
                        {:else}
                            {alert.confirm_text || "지시를 숙지하였습니다"}
                        {/if}
                    </button>
                    {#if timers[alert.id] === 0 || alert.level < 4}
                        <button
                            class="btn-never-show"
                            transition:fade
                            onclick={() => neverShowAgain(alert.id)}
                        >
                            다시 보이지 않음
                        </button>
                    {/if}
                </div>
            </div>
        </div>
    {:else if alert.level >= 3}
        <!-- 🏛️ Level 3, 4: 프리미엄 모달 -->
        <div class="alert-backdrop" transition:fade>
            <div
                class="alert-content card {alert.level === 4
                    ? 'pulse-anim'
                    : ''}"
                use:initTimer={alert}
                transition:fly={{ y: 20 }}
            >
                <div class="text-center">
                    <div
                        class="icon-badge bg-{alert.style}-light text-{alert.style} mb-3"
                    >
                        {alert.level === 4 ? "🚨" : "📢"}
                    </div>
                    <div class="text-muted extra-small mb-2">
                        {getCreatedTimeStr(alert.create_date)}
                    </div>
                    <h5
                        class="fw-bold mb-4 text-dark"
                        style="white-space: pre-line;"
                    >
                        {alert.message}
                    </h5>
                    <button
                        class="btn btn-{alert.style} w-100 py-3 fw-bold rounded-4 mb-3"
                        onclick={() => handleConfirm(alert)}
                    >
                        {#if penaltyMsg[alert.id]}
                            <span>{penaltyMsg[alert.id]}</span>
                        {:else if timers[alert.id] > 0}
                            <span>{timers[alert.id]}초 기다림</span>
                        {:else}
                            {alert.confirm_text}
                        {/if}
                    </button>
                    {#if timers[alert.id] === 0 || alert.level < 4}
                        <button
                            class="btn btn-link btn-sm text-secondary text-decoration-none"
                            transition:fade
                            onclick={() => neverShowAgain(alert.id)}
                        >
                            다시 보지 않기
                        </button>
                    {/if}
                </div>
            </div>
        </div>
    {:else if alert.level === 2}
        <!-- 🚩 Level 2: 가로 배너 -->
        <div class="shimmer-banner alert-{alert.style}" transition:slide>
            <div
                class="container d-flex align-items-center justify-content-between py-2"
            >
                <div class="d-flex align-items-center gap-2 overflow-hidden">
                    <span class="badge bg-white text-{alert.style}">중요</span>
                    <span class="fw-bold text-truncate">{alert.message}</span>
                </div>
                <div class="d-flex gap-2">
                    <button
                        class="btn btn-sm btn-light border py-1 px-3 fw-bold"
                        onclick={() => neverShowAgain(alert.id)}>X</button
                    >
                </div>
            </div>
        </div>
    {:else}
        <!-- 🍞 Level 1: 토스트 (1.5배) -->
        <div
            class="premium-toast toast-{alert.position} alert-{alert.style}"
            transition:fly={{
                y: alert.position === "bottom" ? 80 : -80,
                duration: 800,
            }}
        >
            <div
                class="d-flex align-items-center justify-content-between gap-4 w-100"
            >
                <span class="toast-text">{alert.message}</span>
                <button
                    class="btn-close btn-close-white"
                    style="transform: scale(1.0);"
                    onclick={() => neverShowAgain(alert.id)}
                    aria-label="영구 삭제 및 다시 보지 않기"
                ></button>
            </div>
        </div>
    {/if}
{/each}

<style>
    /* CSS 스타일링은 이전과 동일 */
    .emergency-overlay {
        position: fixed;
        inset: 0;
        background: #000;
        z-index: 20000;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .emergency-container {
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        background: radial-gradient(circle at center, #220000 0%, #000 100%);
        color: #fff;
    }
    .emergency-header {
        background: #d63031;
        padding: 20px;
        text-align: center;
        font-size: 1.4rem;
        font-weight: 900;
    }
    .emergency-body {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 40px;
    }
    .message-text {
        font-size: 3rem;
        line-height: 1.3;
        font-weight: 800;
        text-align: center;
    }
    .emergency-footer {
        padding: 40px;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 20px;
    }
    .btn-primary-emergency {
        width: 100%;
        max-width: 500px;
        background: #ee5253;
        color: #fff;
        border: none;
        padding: 25px;
        font-size: 1.5rem;
        font-weight: 800;
        border-radius: 12px;
    }
    .btn-never-show {
        background: none;
        border: none;
        color: #888;
        text-decoration: underline;
        font-size: 1rem;
    }
    .pulse-text {
        animation: pulseText 2s infinite;
    }
    @keyframes pulseText {
        0%,
        100% {
            opacity: 1;
        }
        50% {
            opacity: 0.7;
        }
    }
    .pulse-anim {
        animation: pulseModal 2s infinite;
    }
    @keyframes pulseModal {
        0% {
            transform: scale(1);
            box-shadow: 0 0 0 0 rgba(214, 48, 49, 0.4);
        }
        70% {
            transform: scale(1.02);
            box-shadow: 0 0 0 20px rgba(214, 48, 49, 0);
        }
        100% {
            transform: scale(1);
            box-shadow: 0 0 0 0 rgba(214, 48, 49, 0);
        }
    }
    .alert-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.8);
        backdrop-filter: blur(10px);
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .alert-content {
        width: 92%;
        max-width: 400px;
        background: white;
        border-radius: 24px;
        padding: 30px;
    }
    .icon-badge {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto;
        font-size: 1.8rem;
    }
    .shimmer-banner {
        width: 100%;
        color: white;
        position: relative;
        overflow: hidden;
    }
    .shimmer-banner::after {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(
            90deg,
            transparent,
            rgba(255, 255, 255, 0.3),
            transparent
        );
        animation: shimmer 3s infinite;
    }
    @keyframes shimmer {
        0% {
            transform: translateX(-100%);
        }
        100% {
            transform: translateX(100%);
        }
    }
    .premium-toast {
        position: fixed;
        left: 50%;
        transform: translateX(-50%);
        z-index: 10001;
        border-radius: 100px;
        padding: 22px 55px;
        font-weight: 800;
        font-size: 1.45rem;
        color: white;
        min-width: 500px;
        box-shadow: 0 15px 45px rgba(0, 0, 0, 0.4);
        border: 2px solid rgba(255, 255, 255, 0.2);
    }
    .toast-text {
        flex: 1;
        text-align: center;
    }
    .toast-top {
        top: 60px;
    }
    .toast-bottom {
        bottom: 60px;
    }
    .bg-danger-light {
        background: #fff5f5;
    }
    .bg-warning-light {
        background: #fffcf0;
    }
    .bg-info-light {
        background: #f0f7ff;
    }
    .alert-info {
        background: #0984e3;
    }
    .alert-success {
        background: #00b894;
    }
    .alert-warning {
        background: #fdcb6e;
        color: #2d3436;
    }
    .alert-danger {
        background: #d63031;
    }
</style>
