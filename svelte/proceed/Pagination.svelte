<script>
    // Svelte 5의 $props 룬을 사용하여 부모로부터 props를 받습니다.
    // 구조 분해 할당을 통해 기본값을 설정할 수 있습니다.
    let { total = 0, currentPage = 0, size = 10, keyword = "" } = $props();

    // $derived 룬을 사용하여 total이나 size가 변경될 때마다
    // totalPages를 자동으로 다시 계산합니다.
    const totalPages = $derived(Math.ceil(total / size));

    // 검색어를 포함한 URL 생성 함수
    const getUrl = (page) => {
        const params = new URLSearchParams({ page: page.toString() });
        if (keyword) params.set("keyword", keyword);
        return `?${params.toString()}`;
    };
</script>

{#if totalPages > 1}
    <ul class="pagination justify-content-center pagination-sm">
        <!-- 이전 페이지 버튼 -->
        <li class="page-item" class:disabled={currentPage <= 0}>
            <a class="page-link" href={getUrl(currentPage - 1)}>이전</a>
        </li>

        <!-- 페이지 번호 목록 -->
        {#each Array(totalPages) as _, i}
            <!-- 현재 페이지를 중심으로 5개씩만 표시 -->
            {#if i >= currentPage - 5 && i <= currentPage + 5}
                <li class="page-item" class:active={i === currentPage}>
                    <a class="page-link" href={getUrl(i)}>{i + 1}</a>
                </li>
            {/if}
        {/each}

        <!-- 다음 페이지 버튼 -->
        <li class="page-item" class:disabled={currentPage + 1 >= totalPages}>
            <a class="page-link" href={getUrl(currentPage + 1)}>다음</a>
        </li>
    </ul>
{/if}
