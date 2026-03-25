<script>
    import { onMount, untrack } from "svelte";
    import { fade, fly } from "svelte/transition";
    import * as api from "$lib/board.api";
    import * as engines from "$lib/index";
    import TiptapEditor from "./TiptapEditor.svelte";

    /** @type {{ slug: string, appId: string }} */
    let { slug, appId } = $props();

    // --- [상태 관리] ---
    let mode = $state("list"); // 'list' | 'view' | 'write' | 'edit'
    let boardSlug = $state("");
    let postId = $state(null);

    let posts = $state([]);
    let board = $state(null);
    let post = $state(null);
    let bindings = $state([]);
    let total = $state(0);
    let isLoading = $state(true);
    let errorMessage = $state("");

    // 작성/수정 폼 데이터
    let editForm = $state({
        title: "",
        content: "",
        content_json: null,
        extra_data: {},
    });

    // 페이징 및 검색
    let currentPage = $state(0);
    let pageSize = $state(10);
    let keyword = $state("");

    import { browser } from '$app/environment';

    // --- [경로 파싱] ---
    function parsePath() {
        if (!browser || !slug) return;

        const parts = slug.split("/");
        boardSlug = parts[0];

        // [혁신적 라우팅] /Slug, /Slug/write, /Slug/postId, /Slug/postId/edit
        if (parts.length === 1) {
            mode = "list";
        } else if (parts[1] === "write") {
            mode = "write";
        } else if (parts[1] && !isNaN(parts[1])) {
            postId = parts[1];
            // postId 뒤에 edit이 붙으면 수정 모드
            if (parts[2] === "edit") {
                mode = "edit";
            } else {
                mode = "view";
            }
        } else {
            mode = "list";
        }
    }

    // --- [데이터 로드] ---
    async function loadData() {
        isLoading = true;
        errorMessage = "";
        try {
            if (mode === "list") {
                const data = await api.getBoardPosts(
                    boardSlug,
                    currentPage,
                    pageSize,
                    keyword,
                );
                posts = data.posts || [];
                board = data.board || null;
                total = data.total || 0;
            } else if (mode === "view") {
                const data = await api.getPostDetail(postId);
                console.log("[BoardEngine] API Response:", data); // [디버깅] API 응답 데이터 확인
                post = data.post;
                board = data.board;
                bindings = data.bindings;
            } else if (mode === "edit") {
                const data = await api.getPostDetail(postId);
                post = data.post;
                // 폼 초기화
                editForm = {
                    title: post.title,
                    content: post.content,
                    content_json: post.content_json,
                    extra_data: post.extra_data || {},
                };
            }
        } catch (e) {
            console.error("Engine Load Error:", e);
            errorMessage = e.message;
        } finally {
            isLoading = false;
        }
    }

    async function handleSave() {
        if (!editForm.title.trim()) return alert("제목을 입력하세요.");

        try {
            isLoading = true;
            if (mode === "write") {
                await api.createPost(boardSlug, editForm);
            } else if (mode === "edit") {
                await api.updatePost(postId, editForm);
            }
            // 성공 시 목록으로 이동
            location.href = `/v1/app/${appId}/${boardSlug}`;
        } catch (e) {
            alert("저장 실패: " + e.message);
        } finally {
            isLoading = false;
        }
    }

    async function handleDelete() {
        if (!confirm("정말 이 게시물을 삭제하시겠습니까?")) return;
        try {
            isLoading = true;
            await api.deletePost(postId);
            alert("게시물이 삭제되었습니다.");
            location.href = `/v1/app/${appId}/${boardSlug}`;
        } catch (e) {
            alert("삭제 실패: " + e.message);
        } finally {
            isLoading = false;
        }
    }

    function goToEdit() {
        location.href = `/v1/app/${appId}/${boardSlug}/${postId}/edit`;
    }

    // --- [핸들러] ---
    function handleSearch(e) {
        e.preventDefault();
        currentPage = 0;
        loadData();
    }

    function changePage(p) {
        currentPage = p;
        loadData();
    }

    // --- [반응형 로직] ---
    // [v1.5.3] 주소 변경 시 즉각적인 데이터 초기화 및 강제 로딩
    $effect(() => {
        if (slug) {
            // 1. 기존 데이터 즉시 비우기 (이전 데이터 잔상 및 멈춤 방지)
            posts = [];
            board = null;
            post = null;
            isLoading = true;
            errorMessage = "";

            untrack(() => {
                parsePath();
                loadData();
            });
        }
    });
</script>

<div class="engine-container" in:fade>
    {#if isLoading && (mode === "list" ? !board : !post)}
        <div class="text-center py-5">
            <div class="spinner-grow text-primary" role="status"></div>
            <p class="mt-3 text-muted">엔진 가동 중...</p>
        </div>
    {:else if errorMessage}
        <div class="container py-5">
            <div
                class="alert alert-warning border-0 shadow-sm d-flex align-items-center"
            >
                <i class="bi bi-exclamation-triangle-fill fs-4 me-3"></i>
                <div>
                    <h4 class="alert-heading h6 fw-bold mb-1">앱 실행 오류</h4>
                    <p class="mb-0 small">{errorMessage}</p>
                </div>
                <button
                    class="btn btn-outline-warning btn-sm ms-auto"
                    onclick={() => history.back()}>뒤로가기</button
                >
            </div>
        </div>
    {:else if mode === "list" && board}
        <!-- --------------------------------------------------------- -->
        <!-- 리스트 뷰 (Premium Design) -->
        <!-- --------------------------------------------------------- -->
        <div class="container py-4">
            <div
                class="row mb-4 align-items-end"
                in:fly={{ y: -20, duration: 500 }}
            >
                <div class="col">
                    <nav aria-label="breadcrumb">
                        <ol
                            class="breadcrumb mb-1 small text-uppercase fw-bold"
                        >
                            <li class="breadcrumb-item text-primary">
                                APP ENGINE
                            </li>
                            <li
                                class="breadcrumb-item active"
                                aria-current="page"
                            >
                                {board.name}
                            </li>
                        </ol>
                    </nav>
                    <h1 class="h3 fw-bold text-dark mb-1">{board.name}</h1>
                    <p class="text-muted small mb-0">
                        {board.description || "앱 엔진으로 구동 중입니다."}
                    </p>
                </div>
                <div class="col-auto">
                    <a
                        href="/v1/app/{appId}/{boardSlug}/write"
                        class="btn btn-primary shadow-sm px-4 rounded-pill"
                    >
                        <i class="bi bi-pencil-square me-2"></i> 글쓰기
                    </a>
                </div>
            </div>

            <div class="card border-0 shadow-sm mb-4 rounded-4">
                <div class="card-body py-2 px-3">
                    <form
                        onsubmit={handleSearch}
                        class="row g-2 align-items-center"
                    >
                        <div class="col-auto">
                            <span class="text-muted small"
                                >Total <strong>{total}</strong></span
                            >
                        </div>
                        <div class="col"></div>
                        <div class="col-auto">
                            <div
                                class="input-group input-group-sm border rounded-pill overflow-hidden px-2 py-1 bg-light"
                            >
                                <span
                                    class="input-group-text bg-transparent border-0"
                                    ><i class="bi bi-search text-muted"
                                    ></i></span
                                >
                                <input
                                    type="text"
                                    class="form-control bg-transparent border-0 shadow-none"
                                    placeholder="검색어 입력..."
                                    bind:value={keyword}
                                />
                                <button
                                    class="btn btn-primary btn-sm rounded-pill px-3 ms-2"
                                    type="submit">검색</button
                                >
                            </div>
                        </div>
                    </form>
                </div>
            </div>

            <div class="card border-0 shadow-sm overflow-hidden mb-4 rounded-4">
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                        <thead
                            class="bg-gradient-primary text-white small text-uppercase shadow-sm"
                        >
                            <tr>
                                <th
                                    class="ps-4 py-3 d-none d-md-table-cell"
                                    style="width: 80px;">ID</th
                                >
                                <th class="py-3">제목</th>
                                <th class="py-3" style="width: 120px;"
                                    >작성자</th
                                >
                                <th
                                    class="py-3 text-center d-none d-sm-table-cell"
                                    style="width: 120px;">작성일</th
                                >
                                <th
                                    class="pe-4 py-3 text-center d-none d-md-table-cell"
                                    style="width: 80px;">조회</th
                                >
                            </tr>
                        </thead>
                        <tbody>
                            {#each posts as it}
                                <tr
                                    class="cursor-pointer"
                                    onclick={() =>
                                        (location.href = `/v1/app/${appId}/${boardSlug}/${it.id}`)}
                                >
                                    <td
                                        class="ps-4 py-3 text-muted small d-none d-md-table-cell"
                                        >{it.id}</td
                                    >
                                    <td class="py-3">
                                        <div
                                            class="d-flex flex-column flex-sm-row align-items-start align-items-sm-center"
                                        >
                                            <div
                                                class="d-flex align-items-center mb-1 mb-sm-0"
                                            >
                                                {#if !it.is_read}
                                                    <span
                                                        class="badge bg-danger rounded-circle p-1 me-2"
                                                        style="width: 6px; height: 6px;"
                                                    ></span>
                                                {/if}
                                                <span class="fw-bold text-dark"
                                                    >{it.title}</span
                                                >
                                                {#if it.comment_count > 0}
                                                    <span
                                                        class="badge bg-primary-subtle text-primary ms-2 rounded-pill small"
                                                    >
                                                        {it.comment_count}
                                                    </span>
                                                {/if}
                                            </div>
                                            <!-- 모바일 전용 날짜 표시 -->
                                            <div
                                                class="d-sm-none text-muted smallest mt-1"
                                            >
                                                <i class="bi bi-clock me-1"></i>
                                                {new Date(
                                                    it.create_date,
                                                ).toLocaleDateString()} · 조회 {it.view_count}
                                            </div>
                                        </div>
                                    </td>
                                    <td class="py-3">
                                        <div class="d-flex align-items-center">
                                            <div
                                                class="avatar-xs bg-light rounded-circle text-center me-2 d-none d-sm-flex align-items-center justify-content-center"
                                            >
                                                <i
                                                    class="bi bi-person text-muted smallest"
                                                ></i>
                                            </div>
                                            <span
                                                class="small fw-semibold text-secondary"
                                                >{it.user_name ||
                                                    it.user?.username ||
                                                    "익명"}</span
                                            >
                                        </div>
                                    </td>
                                    <td
                                        class="py-3 text-center text-muted small d-none d-sm-table-cell"
                                    >
                                        {new Date(
                                            it.create_date,
                                        ).toLocaleDateString()}
                                    </td>
                                    <td
                                        class="pe-4 py-3 text-center text-muted small d-none d-md-table-cell"
                                    >
                                        {it.view_count}
                                    </td>
                                </tr>
                            {:else}
                                <tr>
                                    <td
                                        colspan="5"
                                        class="py-5 text-center text-muted"
                                        >게물 없습니다.</td
                                    >
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            </div>

            {#if total > pageSize}
                <nav>
                    <ul class="pagination pagination-sm justify-content-center">
                        {#each Array(Math.ceil(total / pageSize)) as _, i}
                            <li
                                class="page-item {currentPage === i
                                    ? 'active'
                                    : ''}"
                            >
                                <button
                                    class="page-link border-0 shadow-none rounded-circle mx-1"
                                    onclick={() => changePage(i)}
                                >
                                    {i + 1}
                                </button>
                            </li>
                        {/each}
                    </ul>
                </nav>
            {/if}
        </div>
    {:else if mode === "view" && post}
        <!-- --------------------------------------------------------- -->
        <!-- 상세 뷰 (Premium Design) -->
        <!-- --------------------------------------------------------- -->
        <div class="container py-5" in:fade={{ duration: 400 }}>
            <div class="row justify-content-center">
                <div class="col-lg-11 col-xl-10">
                    <!-- 상단 액션바 -->
                    <div
                        class="d-flex justify-content-between align-items-center mb-4 pb-2 border-bottom border-light"
                    >
                        <div class="d-flex align-items-center gap-3">
                            <a
                                href="/v1/app/{appId}/{boardSlug}"
                                class="btn btn-light rounded-pill px-3 py-2 btn-sm shadow-sm hover-translate"
                            >
                                <i class="bi bi-arrow-left-short fs-5"></i>
                                <span class="d-none d-sm-inline ms-1"
                                    >목록으로</span
                                >
                            </a>
                            <div
                                class="vr h-50 my-auto text-muted opacity-25"
                            ></div>
                            <nav
                                aria-label="breadcrumb"
                                class="d-none d-md-block"
                            >
                                <ol
                                    class="breadcrumb mb-0 small text-uppercase"
                                >
                                    <li
                                        class="breadcrumb-item text-muted fw-semibold"
                                    >
                                        App
                                    </li>
                                    <li
                                        class="breadcrumb-item active text-primary fw-bold"
                                        aria-current="page"
                                    >
                                        {post.board?.name}
                                    </li>
                                </ol>
                            </nav>
                        </div>

                        <div class="d-flex gap-2">
                            <button
                                class="btn btn-outline-secondary btn-sm rounded-pill px-3 shadow-none border-0 hover-bg-light"
                            >
                                <i class="bi bi-share"></i>
                            </button>
                            <button
                                class="btn btn-outline-danger btn-sm rounded-pill px-3 shadow-none border-0 hover-bg-light"
                            >
                                <i class="bi bi-heart"></i>
                            </button>
                        </div>
                    </div>

                    <article
                        class="card border-0 shadow-lg-soft overflow-hidden rounded-5"
                    >
                        <!-- 아티클 헤더 -->
                        <header
                            class="card-header bg-white p-4 p-md-5 border-bottom-0 pb-0"
                        >
                            <div class="mb-4">
                                <span
                                    class="badge bg-gradient-primary text-white px-3 py-2 rounded-pill shadow-sm"
                                >
                                    {post.board?.name || "기본 게시판"}
                                </span>
                            </div>

                            <h1
                                class="display-5 fw-extra-bold text-dark mb-4 tight-tracking"
                            >
                                {post.title}
                            </h1>

                            <!-- 메타 정보 바 -->
                            <div
                                class="d-flex flex-wrap align-items-center justify-content-between py-4 border-top border-bottom border-light-subtle gap-3"
                            >
                                <div class="d-flex align-items-center">
                                    <div
                                        class="avatar-md bg-primary-subtle text-primary rounded-circle me-3 d-flex align-items-center justify-content-center shadow-sm"
                                    >
                                        <i class="bi bi-person-fill fs-4"></i>
                                    </div>
                                    <div>
                                        <div
                                            class="fw-bold text-dark leading-none mb-1"
                                        >
                                            {post.user?.real_name ||
                                                post.user?.username ||
                                                "익명 사용자"}
                                        </div>
                                        <div class="text-muted small">
                                            Post Author
                                        </div>
                                    </div>
                                </div>

                                <div
                                    class="d-flex align-items-center gap-4 text-muted"
                                >
                                    <div class="text-center">
                                        <div
                                            class="small fw-semibold opacity-75"
                                        >
                                            DATE
                                        </div>
                                        <div
                                            class="fw-bold text-dark-emphasis small"
                                        >
                                            {new Date(
                                                post.create_date,
                                            ).toLocaleDateString()}
                                        </div>
                                    </div>
                                    <div class="text-center">
                                        <div
                                            class="small fw-semibold opacity-75"
                                        >
                                            VIEWS
                                        </div>
                                        <div
                                            class="fw-bold text-dark-emphasis small"
                                        >
                                            {post.view_count.toLocaleString()} 회
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </header>

                        <div class="card-body p-4 p-md-5">
                            <!-- 커스텀 필드 (Extra Data) -->
                            {#if post.extra_data && Object.keys(post.extra_data).length > 0}
                                <div
                                    class="bg-primary-subtle bg-opacity-10 rounded-4 p-4 mb-5 border-start border-primary border-5 shadow-sm"
                                >
                                    <h6
                                        class="fw-bold text-primary mb-4 d-flex align-items-center"
                                    >
                                        <span
                                            class="bg-primary text-white rounded-circle p-1 me-2 d-inline-flex align-items-center justify-content-center"
                                            style="width:24px; height:24px;"
                                        >
                                            <i
                                                class="bi bi-info-circle-fill"
                                                style="font-size:0.8rem;"
                                            ></i>
                                        </span>
                                        Additional Information
                                    </h6>
                                    <div class="row g-4">
                                        {#each Object.entries(post.extra_data) as [key, value]}
                                            <div
                                                class="col-6 col-md-4 col-lg-3"
                                            >
                                                <div
                                                    class="text-muted small text-uppercase mb-2 fw-bold opacity-75"
                                                >
                                                    {key}
                                                </div>
                                                <div class="fw-bold text-dark">
                                                    {value}
                                                </div>
                                            </div>
                                        {/each}
                                    </div>
                                </div>
                            {/if}

                            <!-- 본문 영역 -->
                            <div class="tiptap-content-v2">
                                {@html post.content ||
                                    '<p class="text-muted text-center py-5 italic">내용이 비어 있습니다.</p>'}
                            </div>

                            <!-- 태그 섹션 -->
                            {#if post.tags && post.tags.length > 0}
                                <div class="mt-5 pt-4 d-flex flex-wrap gap-2">
                                    {#each post.tags as tag}
                                        <span
                                            class="badge bg-light text-secondary border px-3 py-2 rounded-pill hover-bg-primary-subtle transition-all cursor-pointer"
                                        >
                                            # {tag.name}
                                        </span>
                                    {/each}
                                </div>
                            {/if}

                            <!-- 하단 관리 도구 -->
                            <div
                                class="mt-5 pt-4 border-top d-flex flex-wrap gap-2 justify-content-between align-items-center"
                            >
                                <div class="d-flex gap-2">
                                    <button
                                        class="btn btn-outline-light text-muted border-0 hover-text-primary px-3 rounded-pill btn-sm"
                                    >
                                        <i class="bi bi-flag me-1"></i> 신고
                                    </button>
                                </div>
                                <div class="d-flex gap-2">
                                    <button
                                        class="btn btn-glass-dark btn-sm px-4 py-2 rounded-pill fw-bold shadow-sm"
                                        onclick={goToEdit}
                                    >
                                        <i class="bi bi-pencil-square me-2"></i>
                                        Edit Post
                                    </button>
                                    <button
                                        class="btn btn-outline-danger btn-sm px-4 py-2 rounded-pill fw-bold border-2"
                                        onclick={handleDelete}
                                    >
                                        <i class="bi bi-trash3 me-2"></i> Delete
                                    </button>
                                </div>
                            </div>
                        </div>
                    </article>

                    <!-- [핵심] 서비스 바인딩 영역 -->
        <div class="mt-5">
            {#if post && post.bindings}
                {#each post.bindings as binding}
                    <div class="service-wrapper mb-4 card border-0 shadow-sm">
                        <div class="card-body">
                            <!-- svelte-ignore svelte_component_deprecated -->
                            <svelte:component this={engines[binding.engine.frontend_plugin]} {post} />
                        </div>
                    </div>
                {/each}
            {/if}
        </div>

                    <!-- 다음글/이전글 (Placeholder) -->
                    <div class="row mt-5 g-4">
                        <div class="col-md-6">
                            <div
                                class="p-4 bg-white rounded-4 shadow-sm border border-light-subtle h-100 opacity-75"
                            >
                                <div class="text-muted small mb-1 fw-bold">
                                    PREVIOUS POST
                                </div>
                                <div class="fw-bold">이전 글이 없습니다.</div>
                            </div>
                        </div>
                        <div class="col-md-6 text-end">
                            <div
                                class="p-4 bg-white rounded-4 shadow-sm border border-light-subtle h-100 opacity-75"
                            >
                                <div class="text-muted small mb-1 fw-bold">
                                    NEXT POST
                                </div>
                                <div class="fw-bold">다음 글이 없습니다.</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    {:else if (mode === "write" || mode === "edit") && (mode === "write" || post)}
        <!-- --------------------------------------------------------- -->
        <!-- 작성/수정 뷰 (Premium Design) -->
        <!-- --------------------------------------------------------- -->
        <div class="container py-5" in:fade={{ duration: 400 }}>
            <div class="row justify-content-center">
                <div class="col-lg-10">
                    <div
                        class="d-flex justify-content-between align-items-center mb-4 pb-2"
                    >
                        <div>
                            <nav aria-label="breadcrumb">
                                <ol
                                    class="breadcrumb mb-1 small text-uppercase fw-bold"
                                >
                                    <li class="breadcrumb-item text-primary">
                                        APP ENGINE
                                    </li>
                                    <li class="breadcrumb-item active">
                                        {mode === "write"
                                            ? "새 글 작성"
                                            : "글 수정"}
                                    </li>
                                </ol>
                            </nav>
                            <h2 class="h3 fw-extra-bold text-dark mb-0">
                                {mode === "write"
                                    ? "Create New Post"
                                    : "Edit Post"}
                            </h2>
                        </div>
                        <div class="d-flex gap-2">
                            <button
                                class="btn btn-light rounded-pill px-4 btn-sm fw-bold border"
                                onclick={() => history.back()}>취소</button
                            >
                            <button
                                class="btn btn-primary rounded-pill px-4 btn-sm fw-bold shadow-sm"
                                onclick={handleSave}
                            >
                                <i class="bi bi-check-lg me-2"></i>
                                {mode === "write" ? "등록하기" : "수정완료"}
                            </button>
                        </div>
                    </div>

                    <div
                        class="card border-0 shadow-lg-soft rounded-5 overflow-hidden"
                    >
                        <div class="card-body p-4 p-md-5">
                            <div class="mb-4">
                                <label
                                    for="post-title-input"
                                    class="form-label small fw-bold text-muted text-uppercase tracking-wider"
                                    >Title</label
                                >
                                <input
                                    id="post-title-input"
                                    type="text"
                                    class="form-control form-control-lg border-0 border-bottom rounded-0 px-0 fw-bold fs-3 tight-tracking shadow-none"
                                    style="border-color: #eee !important;"
                                    placeholder="제목을 입력하세요"
                                    bind:value={editForm.title}
                                />
                            </div>

                            <div class="mb-4">
                                <label
                                    for="tiptap-editor"
                                    class="form-label small fw-bold text-muted text-uppercase tracking-wider"
                                    >Content</label
                                >
                                <TiptapEditor
                                    id="tiptap-editor"
                                    bind:content={editForm.content}
                                    bind:content_json={editForm.content_json}
                                />
                            </div>

                            <div class="row g-4 mt-2">
                                <div class="col-md-4">
                                    <label
                                        for="post-status-select"
                                        class="form-label small fw-bold text-muted text-uppercase"
                                        >Status</label
                                    >
                                    <select
                                        id="post-status-select"
                                        class="form-select border-0 bg-light rounded-3 shadow-none"
                                        bind:value={editForm.status}
                                    >
                                        <option value="published"
                                            >공개 (Published)</option
                                        >
                                        <option value="draft"
                                            >임시저장 (Draft)</option
                                        >
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    {/if}
</div>

<style>
    /* --- List & Common --- */
    .cursor-pointer {
        cursor: pointer;
    }

    .avatar-xs {
        width: 20px;
        height: 20px;
        font-size: 0.7rem;
    }
    .smallest {
        font-size: 0.7rem !important;
    }
    .page-link {
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s;
        color: #666;
    }
    .page-item.active .page-link {
        background-color: var(--bs-primary);
        color: white;
        font-weight: bold;
    }

    /* --- Premium Utilities --- */
    .shadow-lg-soft {
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.05);
    }
    .bg-gradient-primary {
        background: linear-gradient(135deg, #0d6efd 0%, #0043a8 100%);
    }
    .fw-extra-bold {
        font-weight: 850;
    }
    .tight-tracking {
        letter-spacing: -0.03em;
    }
    .leading-none {
        line-height: 1;
    }
    .avatar-md {
        width: 48px;
        height: 48px;
    }
    .hover-translate {
        transition: transform 0.2s;
    }
    .hover-translate:hover {
        transform: translateX(-3px);
    }
    .hover-bg-light:hover {
        background-color: #f8f9fa;
    }

    /* glassmorphism button */
    .btn-glass-dark {
        background: rgba(33, 37, 41, 0.05);
        backdrop-filter: blur(4px);
        border: 1px solid rgba(0, 0, 0, 0.1);
        transition: all 0.2s;
    }
    .btn-glass-dark:hover {
        background: rgba(33, 37, 41, 1);
        color: white;
    }

    /* TipTap v2 Content Styles */
    .tiptap-content-v2 {
        font-size: 1.125rem;
        line-height: 1.8;
        color: #2d3748;
    }
    .tiptap-content-v2 :global(p) {
        margin-bottom: 1.5rem;
    }
    .tiptap-content-v2 :global(h1),
    .tiptap-content-v2 :global(h2),
    .tiptap-content-v2 :global(h3) {
        color: #1a202c;
        font-weight: 800;
        margin-top: 2.5rem;
        margin-bottom: 1.25rem;
        letter-spacing: -0.02em;
    }
    .tiptap-content-v2 :global(img) {
        max-width: 100%;
        border-radius: 1.5rem;
        margin: 2.5rem 0;
        box-shadow: 0 15px 40px rgba(0, 0, 0, 0.08);
    }
    .tiptap-content-v2 :global(blockquote) {
        border-left: 6px solid #0d6efd;
        padding: 1.5rem 2rem;
        background: #f8fbff;
        border-radius: 0 1rem 1rem 0;
        font-style: italic;
        margin: 2.5rem 0;
    }
</style>
