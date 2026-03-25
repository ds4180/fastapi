<script>
    import { onMount } from 'svelte';
    import * as commentApi from '$lib/comment.api';

    /**
     * @type {{ post: any }}
     */
    let { post } = $props();

    let comments = $state([]);
    let newComment = $state('');
    let loading = $state(true);

    async function loadComments() {
        loading = true;
        try {
            comments = await commentApi.getComments(post.id);
        } catch (e) {
            console.error("댓글 로딩 실패:", e);
        } finally {
            loading = false;
        }
    }

    async function handleCommentSubmit(event) {
        event.preventDefault();
        if (!newComment.trim()) return;
        try {
            await commentApi.createComment(post.id, { content: newComment });
            newComment = '';
            await loadComments(); // 목록 새로고침
        } catch (e) {
            alert("댓글 작성 실패: " + e.message);
        }
    }

    onMount(loadComments);

</script>

<div class="comment-engine-container">
    <h4 class="mb-4 fw-bold">댓글 ({comments.length})</h4>

    <!-- 댓글 작성 폼 -->
    <div class="card mb-4 border-0 bg-light">
        <div class="card-body">
            <form onsubmit={handleCommentSubmit}>
                <textarea class="form-control" rows="3" bind:value={newComment} placeholder="댓글을 입력하세요..."></textarea>
                <div class="text-end mt-2">
                    <button type="submit" class="btn btn-primary btn-sm">댓글 등록</button>
                </div>
            </form>
        </div>
    </div>

    <!-- 댓글 목록 -->
    <div class="comment-list">
        {#if loading}
            <p>댓글을 불러오는 중...</p>
        {:else if comments.length === 0}
            <p class="text-muted">아직 댓글이 없습니다. 첫 댓글을 남겨보세요!</p>
        {:else}
            {#each comments as comment}
                <div class="comment-item d-flex gap-3 mb-4">
                    <div class="flex-shrink-0">
                        <i class="bi bi-person-circle fs-2 text-muted"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="d-flex justify-content-between">
                            <span class="fw-bold">{comment.user.username}</span>
                            <small class="text-muted">{new Date(comment.create_date).toLocaleString()}</small>
                        </div>
                        <p>{comment.content}</p>
                    </div>
                </div>
            {/each}
        {/if}
    </div>
</div>
