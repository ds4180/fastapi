<script>
    import Calendar from "$lib/components/Calendar.svelte";
    import { enhance } from "$app/forms";
    import { formatDateTime } from "$lib/utils.js";
    import Error from "$lib/components/Error.svelte";

    let { data, form } = $props();

    let currentDate = $state(new Date());
    let selectedDates = $state([]);
    let selectedType = $state("ANNUAL"); // 기본값: 연차
    let memo = $state("");
    let error = $state({ detail: [] });

    // 서버 응답 처리
    $effect(() => {
        if (form?.error) {
            error = form.error;
        } else if (form?.success) {
            // 저장 성공 시 선택 초기화
            selectedDates = [];
            memo = "";
            error = { detail: [] };
        }
    });

    function handleDayClick(event) {
        const clickedTimestamp = event.detail.timestamp;

        if (selectedDates.length === 1) {
            if (selectedDates[0] === clickedTimestamp) {
                selectedDates.length = 0;
                return;
            }

            const startDate = selectedDates[0];
            const endDate = clickedTimestamp;
            const [start, end] = [startDate, endDate].sort((a, b) => a - b);

            selectedDates.length = 0;

            let current = start;
            while (current <= end) {
                selectedDates.push(current);
                const nextDate = new Date(current);
                nextDate.setUTCDate(nextDate.getUTCDate() + 1);
                current = nextDate.getTime();
            }
        } else {
            selectedDates.length = 0;
            selectedDates.push(clickedTimestamp);
        }
    }

    function handleNavigate(event) {
        currentDate = new Date(event.detail.year, event.detail.month);
    }

    // 타임스탬프를 YYYY-MM-DD 문자열로 변환
    function timestampToDateString(timestamp) {
        const date = new Date(timestamp);
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    // 저장 전 날짜 변환
    function prepareDatesForSubmit() {
        return selectedDates.map((ts) => timestampToDateString(ts));
    }
</script>

<div class="container my-3">
    <h5 class="my-3 border-bottom pb-2">휴무일 관리</h5>

    <Error {error} />

    <!-- 달력 및 입력 폼 -->
    <div class="row">
        <div class="col-md-8">
            <Calendar
                year={currentDate.getFullYear()}
                month={currentDate.getMonth()}
                {selectedDates}
                on:dayclick={handleDayClick}
                on:navigate={handleNavigate}
            />
        </div>

        <div class="col-md-4">
            <form method="post" action="?/create" use:enhance>
                <input
                    type="hidden"
                    name="dates"
                    value={JSON.stringify(prepareDatesForSubmit())}
                />

                <div class="mb-3">
                    <label class="form-label">휴무 유형</label>
                    <div>
                        <div class="form-check">
                            <input
                                class="form-check-input"
                                type="radio"
                                name="type"
                                value="ANNUAL"
                                bind:group={selectedType}
                                id="typeAnnual"
                            />
                            <label class="form-check-label" for="typeAnnual"
                                >연차</label
                            >
                        </div>
                        <div class="form-check">
                            <input
                                class="form-check-input"
                                type="radio"
                                name="type"
                                value="SICK"
                                bind:group={selectedType}
                                id="typeSick"
                            />
                            <label class="form-check-label" for="typeSick"
                                >병가</label
                            >
                        </div>
                        <div class="form-check">
                            <input
                                class="form-check-input"
                                type="radio"
                                name="type"
                                value="SPECIAL"
                                bind:group={selectedType}
                                id="typeSpecial"
                            />
                            <label class="form-check-label" for="typeSpecial"
                                >경조사</label
                            >
                        </div>
                        <div class="form-check">
                            <input
                                class="form-check-input"
                                type="radio"
                                name="type"
                                value="OFFICIAL"
                                bind:group={selectedType}
                                id="typeOfficial"
                            />
                            <label class="form-check-label" for="typeOfficial"
                                >공가</label
                            >
                        </div>
                    </div>
                </div>

                <div class="mb-3">
                    <label for="memo" class="form-label">메모</label>
                    <textarea
                        class="form-control"
                        name="memo"
                        id="memo"
                        rows="3"
                        bind:value={memo}
                    ></textarea>
                </div>

                <button type="submit" class="btn btn-primary w-100">저장</button
                >
            </form>

            <!-- 선택된 날짜 미리보기 -->
            <div class="mt-3 p-2 border rounded">
                <h6>선택된 날짜 ({selectedDates.length}일)</h6>
                {#if selectedDates.length > 0}
                    <small class="text-muted">
                        {selectedDates
                            .map((ts) => timestampToDateString(ts))
                            .join(", ")}
                    </small>
                {:else}
                    <small class="text-muted">날짜를 선택해주세요</small>
                {/if}
            </div>
        </div>
    </div>

    <!-- 내 휴무일 목록 -->
    <div class="mt-5">
        <h5 class="border-bottom pb-2">내 휴무일 목록 (총 {data.total}건)</h5>

        {#if data.dayoff_list && data.dayoff_list.length > 0}
            <table class="table table-hover">
                <thead class="table-light">
                    <tr>
                        <th>날짜</th>
                        <th>유형</th>
                        <th>상태</th>
                        <th>메모</th>
                        <th>등록일시</th>
                        <th>관리</th>
                    </tr>
                </thead>
                <tbody>
                    {#each data.dayoff_list as dayoff}
                        <tr>
                            <td>{dayoff.date}</td>
                            <td>
                                {#if dayoff.type === "ANNUAL"}
                                    <span class="badge bg-primary">연차</span>
                                {:else if dayoff.type === "SICK"}
                                    <span class="badge bg-warning">병가</span>
                                {:else if dayoff.type === "SPECIAL"}
                                    <span class="badge bg-info">경조사</span>
                                {:else if dayoff.type === "OFFICIAL"}
                                    <span class="badge bg-success">공가</span>
                                {:else}
                                    <span class="badge bg-secondary"
                                        >{dayoff.type}</span
                                    >
                                {/if}
                            </td>
                            <td>
                                {#if dayoff.status === "REQUESTED"}
                                    <span class="badge bg-secondary">신청</span>
                                {:else if dayoff.status === "APPROVED"}
                                    <span class="badge bg-success">승인</span>
                                {:else if dayoff.status === "REJECTED"}
                                    <span class="badge bg-danger">반려</span>
                                {:else if dayoff.status === "CANCELLED"}
                                    <span class="badge bg-dark">취소</span>
                                {:else}
                                    <span class="badge bg-light text-dark"
                                        >{dayoff.status}</span
                                    >
                                {/if}
                            </td>
                            <td>{dayoff.memo || "-"}</td>
                            <td
                                ><small class="text-muted"
                                    >{formatDateTime(dayoff.create_date)}</small
                                ></td
                            >
                            <td>
                                <form
                                    method="post"
                                    action="?/delete"
                                    use:enhance
                                    style="display:inline;"
                                >
                                    <input
                                        type="hidden"
                                        name="dayoff_id"
                                        value={dayoff.id}
                                    />
                                    <button
                                        type="submit"
                                        class="btn btn-sm btn-outline-danger"
                                        onclick={(e) => {
                                            if (
                                                !confirm(
                                                    "정말 취소하시겠습니까?",
                                                )
                                            )
                                                e.preventDefault();
                                        }}
                                    >
                                        취소
                                    </button>
                                </form>
                            </td>
                        </tr>
                    {/each}
                </tbody>
            </table>
        {:else}
            <p class="text-muted">등록된 휴무일이 없습니다.</p>
        {/if}
    </div>
</div>

<style>
    .selected-dates-container {
        margin-top: 2rem;
        padding: 1rem;
        border: 1px solid #ddd;
        border-radius: 8px;
    }
</style>
