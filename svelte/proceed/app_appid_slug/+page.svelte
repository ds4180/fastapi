<script>
    import * as Engines from "$lib"; // index.js에 등록된 컴포넌트들
    import { fade } from "svelte/transition";

    /** @type {import('./$types').PageData} */
    let { data } = $props();

    // DB에 등록된 main_component 문자열을 사용하여 실제 컴포넌트 찾기
    // 예: 'BoardEngine' -> Engines['BoardEngine']
    const TargetComponent = Engines[data.appInfo.main_component];
</script>

<div class="app-viewport" in:fade>
    {#if TargetComponent}
        <!-- 🧩 동적 컴포넌트 끼워 넣기 -->
        <TargetComponent slug={data.slug} appId={data.appInfo.app_id} />
    {:else}
        <div class="container py-5 text-center">
            <div class="alert alert-warning shadow-sm border-0 rounded-4 p-5">
                <h1 class="display-1 mb-4">🧩</h1>
                <h3 class="fw-bold">컴포넌트를 찾을 수 없습니다</h3>
                <p class="text-muted mb-4">
                    App Registry에 등록된 컴포넌트명(<strong
                        >{data.appInfo.main_component}</strong
                    >)이 시스템 엔진 지도(lib/index.js)에 존재하는지 확인하세요.
                </p>
                <a
                    href="/v1/admin/app"
                    class="btn btn-primary px-4 rounded-pill"
                    >App 설정 확인하러 가기</a
                >
            </div>
        </div>
    {/if}
</div>

<style>
    .app-viewport {
        min-height: 70vh;
    }
</style>
