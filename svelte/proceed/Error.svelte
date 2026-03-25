<script>
    // Svelte 5의 $props 룬을 사용하여 부모로부터 error prop을 받습니다.
    let { error = null } = $props();
</script>

{#if error && error.detail}
    {#if typeof error.detail === "string"}
        <div class="alert alert-danger" role="alert">
            <div>
                {error.detail}
            </div>
        </div>
    {:else if Array.isArray(error.detail) && error.detail.length > 0}
        <div class="alert alert-danger" role="alert">
            {#each error.detail as err}
                <div>
                    {#if err.loc && err.loc.length > 1}
                        <strong>{err.loc[1]}</strong> :
                    {/if}
                    {err.msg}
                </div>
            {/each}
        </div>
    {/if}
{/if}
