<script>
    /**
     * @file 상단 메뉴 및 시스템 구조 관리자 (v1.5.6)
     * [v1.5.6] 하위 메뉴 추가/삭제 기능 완전 복구 및 페이지 엔진 인스턴스 연동
     */
    import { onMount } from "svelte";
    import { fade, fly } from "svelte/transition";
    import {
        adminGetMenus,
        adminCreateMenu,
        adminUpdateMenu,
        adminDeleteMenu,
        adminGetApps,
    } from "$lib/admin.api";
    import { adminGetBoards } from "$lib/board.api";
    import { adminGetPages } from "$lib/page.api";
    import Icon from "$lib/components/Icon.svelte";
    import Error from "$lib/components/Error.svelte";

    /** @type {import('./$types').PageData} */
    let { data } = $props();

    // --- [상태 관리] ---
    let menus = $state(data.menus || []);
    let apps = $state([]);
    let boards = $state([]);
    let pages = $state([]);
    let loading = $state(true);
    let error = $state(null);

    let editingMenu = $state({
        id: "",
        parent_id: "",
        title: "",
        icon_name: "bi:link-45deg",
        icon_color: "#666666",
        link_type: "URL",
        external_url: "",
        app_id: "",
        app_instance_id: "",
        page_id: "",
        order: 0,
        is_visible: true,
        min_rank: 0,
    });

    async function loadAllData() {
        loading = true;
        try {
            const [menuRes, appRes, boardRes, pageRes] = await Promise.all([
                adminGetMenus(),
                adminGetApps(),
                adminGetBoards(),
                adminGetPages(),
            ]);
            menus = menuRes;
            apps = appRes;
            boards = boardRes;
            pages = pageRes;
        } catch (e) {
            error = e.message || "데이터 로드 실패";
        } finally {
            loading = false;
        }
    }

    onMount(loadAllData);

    // [복구] 수정 모드 진입
    function startEdit(menu) {
        editingMenu = {
            ...menu,
            parent_id: menu.parent_id || "",
            app_id: menu.app_id || "",
            app_instance_id: menu.app_instance_id || "",
            page_id: menu.page_id || "",
        };
        scrollToForm();
    }

    // [복구] 하위 메뉴 추가 모드
    function addChild(parentId) {
        resetForm();
        editingMenu.parent_id = parentId;
        scrollToForm();
    }

    function resetForm() {
        editingMenu = {
            id: "",
            parent_id: "",
            title: "",
            icon_name: "bi:link-45deg",
            icon_color: "#666666",
            link_type: "URL",
            external_url: "",
            app_id: "",
            app_instance_id: "",
            page_id: "",
            order: 0,
            is_visible: true,
            min_rank: 0,
        };
    }

    function scrollToForm() {
        const el = document.getElementById("menu-form-card");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    async function handleSubmit(e) {
        if (e) e.preventDefault();
        try {
            const submitData = { ...editingMenu };
            submitData.parent_id = submitData.parent_id
                ? parseInt(submitData.parent_id)
                : null;
            submitData.app_id = submitData.app_id || null;
            submitData.app_instance_id = submitData.app_instance_id
                ? parseInt(submitData.app_instance_id)
                : null;
            submitData.page_id = submitData.page_id
                ? parseInt(submitData.page_id)
                : null;

            if (!editingMenu.id) {
                delete submitData.id;
                await adminCreateMenu(submitData);
                alert("새 메뉴가 등록되었습니다. 🚀");
            } else {
                await adminUpdateMenu(editingMenu.id, submitData);
                alert("메뉴가 수정되었습니다. ✨");
            }
            resetForm();
            await loadAllData();
        } catch (e) {
            alert("저장 실패: " + e.message);
        }
    }

    async function deleteMenu(id) {
        if (!confirm("이 메뉴와 모든 하위 메뉴를 삭제하시겠습니까?")) return;
        try {
            await adminDeleteMenu(id);
            alert("삭제되었습니다.");
            await loadAllData();
        } catch (e) {
            alert("삭제 실패: " + e.message);
        }
    }
</script>

<div class="container-fluid mt-4 pb-5 px-md-5" in:fade>
    <div
        class="d-flex justify-content-between align-items-center mb-4 border-bottom pb-3"
    >
        <h2 class="fw-bold text-primary mb-0">🌐 시스템 메뉴 아키텍처 관리</h2>
        <div class="d-flex gap-2">
            <button
                class="btn btn-outline-primary btn-sm px-3 rounded-pill shadow-sm"
                onclick={loadAllData}
            >
                <Icon icon="bi:arrow-clockwise" class="me-1" /> 새로고침
            </button>
            <a
                href="/v1/admin"
                class="btn btn-outline-secondary btn-sm px-3 rounded-pill shadow-sm"
                >관리자 홈</a
            >
        </div>
    </div>

    <div class="row g-4">
        <!-- 🌳 [복구] 메뉴 트리 리스트 (왼쪽) -->
        <div class="col-lg-5">
            <div
                class="card shadow-sm border-0 rounded-4 overflow-hidden h-100"
            >
                <div
                    class="card-header bg-white py-3 d-flex justify-content-between align-items-center border-bottom-0"
                >
                    <h5 class="mb-0 fw-bold">
                        <Icon icon="bi:diagram-3" class="me-2" />메뉴 트리
                    </h5>
                    <button
                        class="btn btn-dark btn-sm rounded-pill px-3"
                        onclick={resetForm}>+ 최상위 추가</button
                    >
                </div>
                <div class="card-body p-3 bg-light bg-opacity-50">
                    {#if loading}
                        <div class="text-center py-5 text-muted small">
                            구조 분석 중...
                        </div>
                    {:else}
                        <div class="menu-tree">
                            {#each menus as menu}
                                <div
                                    class="menu-item border rounded-4 p-3 mb-3 bg-white shadow-sm"
                                    class:active-edit={editingMenu.id ===
                                        menu.id}
                                >
                                    <div
                                        class="d-flex justify-content-between align-items-center"
                                    >
                                        <div
                                            class="d-flex align-items-center gap-3"
                                        >
                                            <Icon
                                                icon={menu.icon_name ||
                                                    "bi:link-45deg"}
                                                width="20"
                                                color={menu.icon_color}
                                            />
                                            <div>
                                                <div class="fw-bold text-dark">
                                                    {menu.title}
                                                </div>
                                                <div
                                                    class="smallest text-muted"
                                                >
                                                    {menu.link_type} | Rank {menu.min_rank}
                                                </div>
                                            </div>
                                        </div>
                                        <div
                                            class="btn-group btn-group-sm rounded-pill overflow-hidden border shadow-sm"
                                        >
                                            <button
                                                class="btn btn-white btn-sm"
                                                onclick={() =>
                                                    addChild(menu.id)}
                                                title="하위 추가"
                                                ><Icon icon="bi:plus" /></button
                                            >
                                            <button
                                                class="btn btn-white btn-sm"
                                                onclick={() => startEdit(menu)}
                                                title="수정"
                                                ><Icon
                                                    icon="bi:pencil"
                                                /></button
                                            >
                                            <button
                                                class="btn btn-white btn-sm text-danger"
                                                onclick={() =>
                                                    deleteMenu(menu.id)}
                                                title="삭제"
                                                ><Icon
                                                    icon="bi:trash"
                                                /></button
                                            >
                                        </div>
                                    </div>

                                    <!-- 하위 메뉴 (Depth 1) -->
                                    {#if menu.sub_menus && menu.sub_menus.length > 0}
                                        <div
                                            class="ms-4 mt-3 ps-3 border-start border-2 border-primary border-opacity-10"
                                        >
                                            {#each menu.sub_menus as sub}
                                                <div
                                                    class="d-flex justify-content-between align-items-center py-2 border-bottom border-dashed {editingMenu.id ===
                                                    sub.id
                                                        ? 'text-primary fw-bold'
                                                        : ''}"
                                                >
                                                    <div class="small">
                                                        <Icon
                                                            icon="bi:arrow-return-right"
                                                            width="12"
                                                            class="opacity-25 me-1"
                                                        />
                                                        {sub.title}
                                                    </div>
                                                    <div
                                                        class="btn-group btn-group-xs"
                                                    >
                                                        <button
                                                            class="btn btn-link text-decoration-none py-0 px-2 xsmall"
                                                            onclick={() =>
                                                                startEdit(sub)}
                                                            >수정</button
                                                        >
                                                        <button
                                                            class="btn btn-link text-danger text-decoration-none py-0 px-2 xsmall"
                                                            onclick={() =>
                                                                deleteMenu(
                                                                    sub.id,
                                                                )}>삭제</button
                                                        >
                                                    </div>
                                                </div>
                                            {/each}
                                        </div>
                                    {/if}
                                </div>
                            {:else}
                                <div class="p-5 text-center text-muted small">
                                    메뉴가 없습니다.
                                </div>
                            {/each}
                        </div>
                    {/if}
                </div>
            </div>
        </div>

        <!-- 📝 [보강] 설정 폼 (오른쪽) -->
        <div class="col-lg-7">
            <div
                class="card shadow border-0 rounded-4 overflow-hidden sticky-top"
                id="menu-form-card"
                style="top: 90px;"
            >
                <div
                    class="card-header py-3 {editingMenu.id
                        ? 'bg-success'
                        : 'bg-dark'} text-white border-0"
                >
                    <h5 class="mb-0 fw-bold text-center">
                        {editingMenu.id
                            ? `✏️ 메뉴 수정: ${editingMenu.title}`
                            : "🆕 신규 메뉴 마스터 등록"}
                    </h5>
                </div>
                <div class="card-body p-4 bg-light">
                    <form onsubmit={handleSubmit}>
                        {#if editingMenu.parent_id}
                            <div
                                class="alert alert-info py-2 small mb-4 d-flex justify-content-between align-items-center rounded-3 border-0"
                            >
                                <span
                                    ><strong>📍 하위 메뉴:</strong> ID
                                    <code>{editingMenu.parent_id}</code> 하위에 등록됩니다.</span
                                >
                                <button
                                    type="button"
                                    class="btn-close"
                                    onclick={() => (editingMenu.parent_id = "")}
                                ></button>
                            </div>
                        {/if}

                        <div class="mb-4">
                            <label class="form-label fw-bold small text-muted"
                                >메뉴 표시 명칭</label
                            >
                            <input
                                type="text"
                                class="form-control form-control-lg border-0 shadow-sm rounded-3"
                                bind:value={editingMenu.title}
                                placeholder="사이트 노출 명칭"
                                required
                            />
                        </div>

                        <div class="row g-3 mb-4">
                            <div class="col-md-6">
                                <label
                                    class="form-label fw-bold small text-muted"
                                    >연결 타입</label
                                >
                                <select
                                    class="form-select border-0 shadow-sm rounded-3 bg-primary bg-opacity-10 fw-bold"
                                    bind:value={editingMenu.link_type}
                                >
                                    <option value="URL"
                                        >🔗 일반 주소 (URL)</option
                                    >
                                    <option value="APP"
                                        >🚀 시스템 App 엔진</option
                                    >
                                    <option value="DIVIDER"
                                        >➖ 메뉴 구분선</option
                                    >
                                </select>
                            </div>
                            <div class="col-md-6">
                                <label
                                    class="form-label fw-bold small text-muted"
                                    >노출 권한 (Rank)</label
                                >
                                <select
                                    class="form-select border-0 shadow-sm rounded-3"
                                    bind:value={editingMenu.min_rank}
                                >
                                    <option value={0}>전체 공개 (Rank 0)</option
                                    >
                                    <option value={1}
                                        >로그인 사용자 (Rank 1)</option
                                    >
                                    <option value={2}>실무자용 (Rank 2)</option>
                                    <option value={3}>관리자용 (Rank 3)</option>
                                    <option value={4}
                                        >최고관리자 (Rank 4)</option
                                    >
                                </select>
                            </div>
                        </div>

                        {#if editingMenu.link_type === "APP"}
                            <div
                                class="mb-4 p-4 border-2 border-primary rounded-4 bg-white shadow-sm"
                                in:fly={{ y: 10 }}
                            >
                                <div class="row g-3">
                                    <div class="col-md-6">
                                        <label
                                            class="small fw-bold text-primary mb-1"
                                            >대상 앱 엔진</label
                                        >
                                        <select
                                            class="form-select border-0 bg-light"
                                            bind:value={editingMenu.app_id}
                                        >
                                            <option value=""
                                                >-- 엔진 선택 --</option
                                            >
                                            {#each apps as app}
                                                <option value={app.app_id}
                                                    >{app.title || app.name} ({app.app_id})</option
                                                >
                                            {/each}
                                        </select>
                                    </div>
                                    <div class="col-md-12">
                                        <label
                                            class="small fw-bold text-primary mb-1"
                                            >🔗 상세 연결 및 관리 모드 선택</label
                                        >
                                        <select
                                            class="form-select border-0 bg-light-subtle shadow-sm"
                                            bind:value={
                                                editingMenu.app_instance_id
                                            }
                                        >
                                            <option value=""
                                                >-- 서비스 기본 화면 (ID: 0) --</option
                                            >
                                            <option
                                                value={-1}
                                                class="text-danger fw-bold"
                                                >🛠️ 해당 엔진 관리 도구 (-1)</option
                                            >
                                            <option disabled>──────────</option>

                                            {#if editingMenu.app_id === "board"}
                                                {#each boards as b}<option
                                                        value={b.id}
                                                        >📑 게시판: {b.name} ({b.slug})</option
                                                    >{/each}
                                            {:else if editingMenu.app_id === "page"}
                                                {#each pages as p}<option
                                                        value={p.id}
                                                        >📄 페이지: {p.title} ({p.slug})</option
                                                    >{/each}
                                            {/if}
                                        </select>
                                    </div>
                                </div>
                                <div
                                    class="form-text mt-3 xsmall text-primary opacity-75 d-flex align-items-center"
                                >
                                    <Icon icon="bi:info-circle" class="me-1" />
                                    <span
                                        >일반 서비스는 <strong
                                            >'기본 화면'</strong
                                        >
                                        혹은 <strong>'각 리스트'</strong>를
                                        선택하고, 설정을 위해서는
                                        <strong>'관리 도구'</strong>를
                                        선택하세요.</span
                                    >
                                </div>
                            </div>
                        {:else if editingMenu.link_type === "URL"}
                            <div class="mb-4">
                                <label
                                    class="form-label fw-bold small text-muted"
                                    >이동 주소 (URL)</label
                                >
                                <input
                                    type="text"
                                    class="form-control border-0 shadow-sm rounded-3"
                                    bind:value={editingMenu.external_url}
                                    placeholder="예: /v1/admin/page"
                                />
                            </div>
                        {/if}

                        <div class="row g-3 mb-4">
                            <div class="col-md-4">
                                <label
                                    class="form-label fw-bold small text-muted"
                                    >정렬 순서</label
                                >
                                <input
                                    type="number"
                                    class="form-control border-0 shadow-sm rounded-3"
                                    bind:value={editingMenu.order}
                                />
                            </div>
                            <div class="col-md-4">
                                <label
                                    class="form-label fw-bold small text-muted"
                                    >아이콘 색상</label
                                >
                                <input
                                    type="color"
                                    class="form-control form-control-color w-100 border-0 shadow-sm rounded-3"
                                    bind:value={editingMenu.icon_color}
                                />
                            </div>
                            <div class="col-md-4 d-flex align-items-end">
                                <div
                                    class="form-check form-switch p-2 bg-white rounded-3 border shadow-sm ps-5 w-100 mb-1"
                                >
                                    <input
                                        class="form-check-input ms-0"
                                        type="checkbox"
                                        id="is_visible"
                                        bind:checked={editingMenu.is_visible}
                                    />
                                    <label
                                        class="form-check-label fw-bold small text-muted ms-2"
                                        for="is_visible">메뉴 활성</label
                                    >
                                </div>
                            </div>
                        </div>

                        <div
                            class="d-flex justify-content-between align-items-center pt-4 border-top gap-2"
                        >
                            <button
                                type="button"
                                class="btn btn-link text-muted text-decoration-none small"
                                onclick={resetForm}>초기화</button
                            >
                            <button
                                type="submit"
                                class="btn {editingMenu.id
                                    ? 'btn-success'
                                    : 'btn-dark'} px-5 py-3 fw-bold rounded-pill shadow-lg"
                            >
                                {editingMenu.id
                                    ? "변경 사항 확정 저장 💾"
                                    : "새 메뉴 마스터 등록 🚀"}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    .active-edit {
        border-left: 5px solid #0d6efd !important;
        background-color: #f0f7ff !important;
    }
    .smallest {
        font-size: 0.65rem;
    }
    .xsmall {
        font-size: 0.7rem;
    }
    .btn-white {
        background: #fff;
        border: 1px solid #dee2e6;
    }
    .btn-white:hover {
        background: #f8f9fa;
    }
    .highlight-form {
        transform: scale(1.01);
        box-shadow: 0 0 30px rgba(13, 110, 253, 0.2) !important;
        transition: all 0.3s ease;
    }
    @media (max-width: 991.98px) {
        .sticky-top {
            position: static !important;
        }
    }
</style>
