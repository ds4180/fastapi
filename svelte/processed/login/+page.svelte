<script>
    import { enhance } from "$app/forms";
    import Error from "$lib/components/Error.svelte";

    let { form } = $props();

    // 폼 제출 실패 시, 입력했던 값을 유지하기 위해 상태를 설정합니다.
    let username = $state(form?.username || "");
    let password = $state("");
    let error = $state({ detail: [] });

    // form prop이 변경될 때마다 에러 상태를 업데이트합니다.
    $effect(() => {
        if (form?.error) {
            error = form.error;
        } else {
            error = { detail: [] };
        }
    });
</script>

<div class="container my-3">
    <h5 class="my-3 border-bottom pb-2">로그인</h5>
    <Error {error} />
    <form method="post" class="my-3" use:enhance>
        <div class="mb-3">
            <label for="username">사용자이름</label>
            <input
                type="text"
                class="form-control"
                name="username"
                id="username"
                bind:value={username}
            />
        </div>
        <div class="mb-3">
            <label for="password">비밀번호</label>
            <input
                type="password"
                class="form-control"
                name="password"
                id="password"
                bind:value={password}
            />
        </div>
        <button type="submit" class="btn btn-primary">로그인</button>
    </form>
</div>
