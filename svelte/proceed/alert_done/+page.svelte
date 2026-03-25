<script>
    import { enhance } from "$app/forms";
    import Error from "$lib/components/Error.svelte";

    /** @type {import('./$types').PageData} */
    let { data, form } = $props();

    let message = $state("");
    let level = $state(1);
    let style = $state("info");
    let position = $state("top");
    let route = $state("");
    let start_date = $state("");
    let end_date = $state("");
    let redirect_url = $state("");
    let reset_sec = $state(5);
    let confirm_text = "확인하였습니다";
    let selectedUsers = $state([]);

    $effect(() => {
        if (form?.success) {
            message = "";
            level = 1;
            style = "info";
            position = "top";
            route = "";
            start_date = "";
            end_date = "";
            redirect_url = "";
            reset_sec = 5;
            selectedUsers = [];
            alert("알림이 성공적으로 송출되었습니다!");
        }
    });

    let isSubmitting = $state(false);

    // 날짜 포맷팅 함수 (화면 표시용)
    function formatDate(iso) {
        if (!iso) return "-";
        return new Date(iso).toLocaleString("ko-KR", {
            year: "2-digit",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function toggleUser(username) {
        if (selectedUsers.includes(username)) {
            selectedUsers = selectedUsers.filter((u) => u !== username);
        } else {
            selectedUsers = [...selectedUsers, username];
        }
    }
</script>

<div class="container my-5">
    <div
        class="d-flex justify-content-between align-items-center border-bottom pb-2 mb-4"
    >
        <h2 class="mb-0">📢 알림 및 기강 잡기 시스템</h2>
        <a href="/" class="btn btn-outline-secondary btn-sm">메인으로</a>
    </div>

    {#if form?.error}<Error error={form.error} />{/if}

    <div class="card shadow-sm mb-5 border-0 rounded-4 overflow-hidden">
        <div class="card-header bg-dark text-white py-3">
            <h5 class="mb-0">새 업무 지시 등록</h5>
        </div>
        <div class="card-body p-4 bg-light">
            <form
                method="POST"
                action="?/create"
                use:enhance={() => {
                    isSubmitting = true;
                    return async ({ update }) => {
                        await update();
                        isSubmitting = false;
                    };
                }}
            >
                <!-- 수신자 목록을 콤마로 구분된 문자열로 전송 -->
                <input
                    type="hidden"
                    name="target_users"
                    value={selectedUsers.join(",")}
                />

                <div class="row g-4">
                    <div class="col-12">
                        <label class="form-label fw-bold"
                            >지시 내용 (핵심 요약)</label
                        >
                        <textarea
                            name="message"
                            class="form-control"
                            rows="3"
                            bind:value={message}
                            placeholder="기사님들에게 노출될 핵심 지시 내용을 입력하세요."
                        ></textarea>
                    </div>

                    <div class="col-md-3">
                        <label class="form-label fw-bold">알림 등급</label>
                        <select
                            name="level"
                            class="form-select"
                            bind:value={level}
                        >
                            <option value={1}>Lv.1 (토스트)</option>
                            <option value={2}>Lv.2 (공간 배너)</option>
                            <option value={3}>Lv.3 (일반 모달)</option>
                            <option value={4}>Lv.4 (정독 모달)</option>
                            <option value={5}>Lv.5 (🚨 비상 점유)</option>
                        </select>
                    </div>

                    <div class="col-md-3">
                        <label class="form-label fw-bold">노출 위치</label>
                        <select
                            name="position"
                            class="form-select"
                            bind:value={position}
                        >
                            <option value="top">상단 (Top)</option>
                            <option value="bottom">하단 (Bottom)</option>
                        </select>
                    </div>

                    <div class="col-md-3">
                        <label class="form-label fw-bold">스타일</label>
                        <select
                            name="style"
                            class="form-select"
                            bind:value={style}
                        >
                            <option value="info">Info (파랑)</option>
                            <option value="success">Success (초록)</option>
                            <option value="warning">Warning (노랑)</option>
                            <option value="danger">Danger (빨강)</option>
                        </select>
                    </div>

                    <div class="col-md-3">
                        <label class="form-label fw-bold">강제 대기(초)</label>
                        <input
                            name="reset_sec"
                            type="number"
                            class="form-control"
                            bind:value={reset_sec}
                            min="0"
                        />
                    </div>

                    <!-- 👥 수신자 선택 영역 -->
                    <div class="col-12">
                        <label class="form-label fw-bold"
                            >수신 대상 (선택하지 않으면 전체 송출)</label
                        >
                        <div
                            class="d-flex flex-wrap gap-2 p-3 bg-white border rounded"
                        >
                            {#each data.users as user}
                                <button
                                    type="button"
                                    class="btn btn-sm rounded-pill {selectedUsers.includes(
                                        user.username,
                                    )
                                        ? 'btn-primary'
                                        : 'btn-outline-secondary'}"
                                    onclick={() => toggleUser(user.username)}
                                >
                                    {user.username}
                                </button>
                            {/each}
                        </div>
                    </div>

                    <div class="col-md-6">
                        <label class="form-label fw-bold text-primary"
                            >시작 일시 (예약)</label
                        >
                        <input
                            name="start_date"
                            type="datetime-local"
                            class="form-control"
                            bind:value={start_date}
                        />
                    </div>

                    <div class="col-md-6">
                        <label class="form-label fw-bold text-danger"
                            >종료 일시 (자동 자동 소멸)</label
                        >
                        <input
                            name="end_date"
                            type="datetime-local"
                            class="form-control"
                            bind:value={end_date}
                        />
                    </div>

                    <div class="col-md-6">
                        <label class="form-label fw-bold"
                            >노출 경로 (예: / , /calendar...)</label
                        >
                        <input
                            name="route"
                            type="text"
                            class="form-control"
                            bind:value={route}
                            placeholder="비워두면 모든 페이지"
                        />
                    </div>

                    <div class="col-md-6">
                        <label class="form-label fw-bold">이동 시킬 URL</label>
                        <input
                            name="redirect_url"
                            type="text"
                            class="form-control"
                            bind:value={redirect_url}
                            placeholder="확인 시 자동 이동"
                        />
                    </div>

                    <div class="col-12 text-end pt-3">
                        <button
                            type="submit"
                            class="btn btn-dark px-5 py-3 fw-bold shadow-sm"
                            disabled={isSubmitting}
                        >
                            {#if isSubmitting}<span
                                    class="spinner-border spinner-border-sm"
                                ></span> 전송 중...{:else}지시 사항 송출하기{/if}
                        </button>
                    </div>
                </div>
            </form>
        </div>
    </div>

    <!-- 목록 테이블 -->
    <h4 class="mb-3 d-flex align-items-center gap-2">
        📂 현재 송출 중인 지시 목록
        <span class="badge bg-secondary rounded-pill fs-7"
            >{data.alerts?.length || 0}</span
        >
    </h4>
    <div class="table-responsive shadow-sm rounded-4 border overflow-hidden">
        <table class="table table-hover align-middle mb-0 bg-white text-center">
            <thead class="table-light">
                <tr>
                    <th>상태</th>
                    <th>내용 / 대상</th>
                    <th>등급</th>
                    <th>위치</th>
                    <th>유효 기간</th>
                    <th>작업</th>
                </tr>
            </thead>
            <tbody>
                {#each data.alerts as alert}
                    <tr>
                        <td>
                            <form method="POST" action="?/toggle" use:enhance>
                                <input
                                    type="hidden"
                                    name="id"
                                    value={alert.id}
                                />
                                <button
                                    type="submit"
                                    class="btn btn-sm {alert.is_active
                                        ? 'btn-success'
                                        : 'btn-outline-secondary'} rounded-pill px-3"
                                >
                                    {alert.is_active ? "활성" : "중지"}
                                </button>
                            </form>
                        </td>
                        <td class="text-start p-3">
                            <div class="fw-bold text-dark">{alert.message}</div>
                            <div class="d-flex flex-wrap gap-1 mt-1">
                                {#if alert.route}
                                    <span
                                        class="badge bg-light text-dark extra-small border"
                                        >📍 {alert.route}</span
                                    >
                                {/if}
                                {#if alert.target_users}
                                    <span class="badge bg-secondary extra-small"
                                        >👥 {alert.target_users}</span
                                    >
                                {:else}
                                    <span class="badge bg-info extra-small"
                                        >👥 전체</span
                                    >
                                {/if}
                            </div>
                        </td>
                        <td
                            ><span class="badge bg-{alert.style}"
                                >Lv.{alert.level}</span
                            ></td
                        >
                        <td>{alert.position === "top" ? "상" : "하"}</td>
                        <td class="small">
                            {formatDate(alert.start_date)}<br />
                            <span class="text-muted">~</span><br />
                            {formatDate(alert.end_date)}
                        </td>
                        <td>
                            <form
                                method="POST"
                                action="?/delete"
                                use:enhance
                                onsubmit={(e) =>
                                    !confirm("완전 삭제하시겠습니까?") &&
                                    e.preventDefault()}
                            >
                                <input
                                    type="hidden"
                                    name="id"
                                    value={alert.id}
                                />
                                <button
                                    type="submit"
                                    class="btn btn-sm text-danger opacity-75"
                                    >삭제</button
                                >
                            </form>
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
</div>

<style>
    .extra-small {
        font-size: 0.75rem;
    }
    .fs-7 {
        font-size: 0.9rem;
    }
</style>
