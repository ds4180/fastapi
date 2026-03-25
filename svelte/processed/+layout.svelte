<script>
    import { onMount } from "svelte";
    import { page } from "$app/stores";
    import Alert from "$lib/components/Alert.svelte";
    import { isQuietMode } from "$lib/store";
    import "bootstrap/dist/css/bootstrap.min.css";

    /** @type {import('./$types').LayoutData} */
    let { data, children } = $props();

    onMount(async () => {
        await import("bootstrap/dist/js/bootstrap.bundle.min.js");
    });

    /**
     * 메뉴 타입에 따른 링크 생성 헬퍼 함수
     */
    function getMenuLink(menu) {
        if (menu.link_type === "BOARD" && menu.board_id) {
            return `/v1/board/${menu.board_id}`;
        } else if (menu.link_type === "PAGE" && menu.page_id) {
            return `/v1/board/page/${menu.page_id}`; // CMS 페이지용 범용 경로
        } else if (menu.link_type === "URL") {
            return menu.external_url || "#";
        }
        return "#";
    }
</script>

<Alert positionFilter="top" />

<nav
    class="navbar navbar-expand-lg navbar-light bg-light border-bottom sticky-top shadow-sm"
>
    <div class="container-fluid">
        <a class="navbar-brand fw-bold text-primary" href="/">jeju.live</a>

        <button
            class="navbar-toggler"
            type="button"
            data-bs-toggle="collapse"
            data-bs-target="#navbarContent"
        >
            <span class="navbar-toggler-icon"></span>
        </button>

        <div class="collapse navbar-collapse" id="navbarContent">
            <ul class="navbar-nav me-auto mb-2 mb-lg-0 mobile-2-col-grid">
                <!-- 🔐 인증 영역 (사용자 요청 로직 반영) -->
                {#if data.username}
                    <li class="nav-item user-item">
                        <div
                            class="nav-link user-banner d-flex align-items-center justify-content-between"
                        >
                            <span>👤 <strong>{data.username}</strong>님</span>
                            <div>
                                <button
                                    class="btn btn-sm rounded-pill px-2 py-0 me-2 {$isQuietMode
                                        ? 'btn-warning'
                                        : 'btn-outline-secondary'}"
                                    onclick={() =>
                                        isQuietMode.update((v) => !v)}
                                >
                                    {$isQuietMode ? "🔕" : "🔔"}
                                </button>
                                <a
                                    href="/user-logout"
                                    class="btn btn-sm btn-outline-danger py-0"
                                    >로그아웃</a
                                >
                            </div>
                        </div>
                    </li>

                    <!-- Rank 1 이상만 보이는 회원가입(사용자 생성) -->
                    {#if data.rankLevel >= 1}
                        <li class="nav-item">
                            <a class="nav-link" href="/user-create">회원등록</a>
                        </li>
                    {/if}
                {:else}
                    <li class="nav-item">
                        <a class="nav-link" href="/user-login">로그인</a>
                    </li>
                {/if}

                <!-- 🏗️ [하드코딩 구역] Core 서비스 -->
                <li class="nav-item">
                    <a
                        class="nav-link"
                        class:active={$page.url.pathname.startsWith(
                            "/calendar",
                        )}
                        href="/calendar">달력</a
                    >
                </li>

                <!-- 🌐 [DB 연동 구역] 동적 CMS 메뉴 -->
                {#each data.dynamicMenus as menu}
                    {#if menu.sub_menus && menu.sub_menus.length > 0}
                        <!-- 하위 메뉴가 있는 경우: 드롭다운 -->
                        <li class="nav-item dropdown">
                            <a
                                class="nav-link dropdown-toggle"
                                href="#"
                                id="navbarDropdown{menu.id}"
                                role="button"
                                data-bs-toggle="dropdown"
                                aria-expanded="false"
                            >
                                {menu.title}
                            </a>
                            <ul
                                class="dropdown-menu shadow-sm"
                                aria-labelledby="navbarDropdown{menu.id}"
                            >
                                {#each menu.sub_menus as sub}
                                    <li>
                                        <a
                                            class="dropdown-item"
                                            href={getMenuLink(sub)}
                                        >
                                            {sub.title}
                                        </a>
                                    </li>
                                {/each}
                            </ul>
                        </li>
                    {:else}
                        <!-- 하위 메뉴가 없는 경우: 단일 링크 -->
                        <li class="nav-item">
                            <a class="nav-link" href={getMenuLink(menu)}>
                                {menu.title}
                            </a>
                        </li>
                    {/if}
                {/each}

                <!-- 최고 관리자 전용 바로가기 -->
                {#if data.rankLevel >= 3}
                    <li class="nav-item alert-item">
                        <a class="nav-link alert-manage-btn" href="/v1/admin"
                            >관리자 🛠️</a
                        >
                    </li>
                {/if}
            </ul>
        </div>
    </div>
</nav>

<main class="container-fluid">
    {@render children()}
</main>

<Alert positionFilter="bottom" />
<Alert positionFilter="modal" />

<style>
    main {
        min-height: 85vh;
        padding: 20px 0;
    }

    /* 📱 모바일 2열 그리드 미디어 쿼리 */
    @media (max-width: 991.98px) {
        .mobile-2-col-grid {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap !important;
            padding: 1rem 0;
        }
        .mobile-2-col-grid .nav-item {
            width: 50% !important;
            padding: 3px;
        }
        .mobile-2-col-grid .user-item,
        .mobile-2-col-grid .alert-item {
            width: 100% !important;
        }
        .nav-link {
            text-align: center;
            border: 1px solid #eee;
            border-radius: 8px;
            margin: 2px;
            background: #fdfdfd;
        }
        .nav-link.active {
            font-weight: bold;
            color: #0d6efd !important;
            background: #e7f1ff;
        }
        .user-banner {
            border-bottom: 1px solid #eee;
            margin-bottom: 10px;
        }
    }

    @media (min-width: 992px) {
        .nav-link {
            padding-left: 15px !important;
            padding-right: 15px !important;
        }
        .alert-manage-btn {
            background-color: #fff3cd;
            color: #856404;
            border-radius: 20px;
            padding: 5px 15px !important;
            margin-left: 10px;
            font-weight: bold;
        }
    }
</style>
