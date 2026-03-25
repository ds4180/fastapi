<script>
    import { onMount } from 'svelte';
    import { 
        adminGetBoards, adminCreateBoard, adminUpdateBoard, adminDeleteBoard,
        adminGetServiceEngines, adminGetServiceBindings, adminCreateServiceBinding, adminDeleteServiceBinding
    } from '$lib/admin.api';
    import Error from '$lib/components/Error.svelte';
    import { fade } from 'svelte/transition';

    // --- 상태 관리 ---
    let boards = $state([]);
    let loading = $state(true);
    let error = $state(null);
    let isEditing = $state(false);

    // --- 폼 데이터 ---
    let formData = $state({});
    function resetForm() {
        formData = { slug: '', name: '', description: '', layout_type: 'list', items_per_page: 10, options: {}, is_active: true };
        isEditing = false;
    }

    // --- 서비스 관리 모달 상태 ---
    let showServiceModal = $state(false);
    let selectedBoard = $state(null);
    let allEngines = $state([]);
    let bindings = $state([]);

    // --- 데이터 로드 ---
    async function loadBoards() {
        loading = true;
        try {
            boards = await adminGetBoards();
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    }

    onMount(loadBoards);

    // --- CRUD 핸들러 ---
    async function handleSubmit(event) {
        event.preventDefault();
        try {
            if (isEditing) {
                await adminUpdateBoard(formData.id, formData);
            } else {
                await adminCreateBoard(formData);
            }
            resetForm();
            await loadBoards();
        } catch (e) {
            alert("저장 실패: " + e.message);
        }
    }

    function editBoard(board) {
        formData = { ...board };
        isEditing = true;
    }

    async function deleteBoard(id) {
        if (!confirm(`게시판을 삭제하시겠습니까?`)) return;
        try {
            await adminDeleteBoard(id);
            await loadBoards();
        } catch (e) {
            alert("삭제 실패: " + e.message);
        }
    }

    // --- 서비스 조립 핸들러 ---
    async function openServiceModal(board) {
        selectedBoard = board;
        showServiceModal = true;
        try {
            const [enginesRes, bindingsRes] = await Promise.all([
                adminGetServiceEngines(),
                adminGetServiceBindings('board', board.id)
            ]);
            allEngines = enginesRes;
            bindings = bindingsRes;
        } catch (e) {
            error = e.message;
        }
    }

    async function handleBindService(engineId) {
        try {
            await adminCreateServiceBinding({ target_app: 'board', target_id: selectedBoard.id, engine_id: engineId });
            // 모달 데이터 다시 로드
            bindings = await adminGetServiceBindings('board', selectedBoard.id);
        } catch (e) {
            alert("조립 실패: " + e.message);
        }
    }

    async function handleUnbindService(bindingId) {
        try {
            await adminDeleteServiceBinding(bindingId);
            bindings = bindings.filter(b => b.id !== bindingId);
        } catch (e) {
            alert("분리 실패: " + e.message);
        }
    }

</script>

<div class="container-fluid py-4 px-4" in:fade>
    <h2 class="fw-bold text-primary mb-4">📋 게시판 인스턴스 관리</h2>

    <div class="row">
        <div class="col-lg-8">
            <div class="card shadow-sm border-0 rounded-4">
                <div class="card-body">
                    <table class="table table-hover">
                        <thead>
                            <tr><th>이름</th><th>슬러그</th><th>레이아웃</th><th>활성</th><th>관리</th></tr>
                        </thead>
                        <tbody>
                            {#each boards as board}
                                <tr>
                                    <td>{board.name}</td>
                                    <td>{board.slug}</td>
                                    <td>{board.layout_type}</td>
                                    <td>{board.is_active ? '✔️' : '❌'}</td>
                                    <td>
                                        <button class="btn btn-sm btn-outline-primary" onclick={() => editBoard(board)}>수정</button>
                                        <button class="btn btn-sm btn-outline-danger" onclick={() => deleteBoard(board.id)}>삭제</button>
                                        <button class="btn btn-sm btn-outline-success" onclick={() => openServiceModal(board)}>🧩 서비스 관리</button>
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        <div class="col-lg-4">
            <div class="card shadow-sm border-0 rounded-4">
                <div class="card-header bg-dark text-white">{isEditing ? '게시판 수정' : '새 게시판 생성'}</div>
                <div class="card-body">
                    <form onsubmit={handleSubmit}>
                        <!-- 폼 필드들 -->
                        <button type="submit" class="btn btn-primary">{isEditing ? '업데이트' : '생성'}</button>
                        {#if isEditing}<button type="button" class="btn btn-secondary" onclick={resetForm}>취소</button>{/if}
                    </form>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- 서비스 관리 모달 -->
{#if showServiceModal}
<div class="modal fade show" style="display: block;" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">🧩 서비스 조립: {selectedBoard.name}</h5>
                <button type="button" class="btn-close" onclick={() => showServiceModal = false}></button>
            </div>
            <div class="modal-body">
                <h6>현재 연결된 서비스</h6>
                <ul>
                    {#each bindings as binding}
                        <li>{binding.engine_id} <button class="btn btn-sm btn-danger" onclick={() => handleUnbindService(binding.id)}>분리</button></li>
                    {/each}
                </ul>
                <hr/>
                <h6>조립 가능한 서비스</h6>
                <ul>
                    {#each allEngines.filter(eng => !bindings.some(b => b.engine_id === eng.id)) as engine}
                        <li>{engine.id} <button class="btn btn-sm btn-success" onclick={() => handleBindService(engine.id)}>조립</button></li>
                    {/each}
                </ul>
            </div>
        </div>
    </div>
</div>
<div class="modal-backdrop fade show"></div>
{/if}
