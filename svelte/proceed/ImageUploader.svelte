<script>
    import fastapi from "$lib/api";
    import { onDestroy } from "svelte";
    import { env } from "$env/dynamic/public";

    const PUBLIC_SERVER_URL = env.PUBLIC_SERVER_URL;

    /**
     * @typedef {Object} Props
     * @property {boolean} [multiple=true] - 여러 파일 선택 가능 여부
     * @property {function} [onUpload] - 업로드 성공 시 호출될 콜백 함수
     * @property {Array} [uploadedFiles] - 상위 페이지와 동기화될 업로드된 파일 목록
     */

    /** @type {Props} */
    let { multiple = true, onUpload, uploadedFiles = $bindable([]) } = $props();

    let files = $state([]); // 선택된 파일 (업로드 대기 중)
    let previewUrls = $state([]); // 대기 중인 파일 미리보기
    let isLoading = $state(false);
    let errorMessage = $state("");

    // 파일 선택 시 호출
    function handleFileChange(e) {
        const selectedFiles = Array.from(e.target.files);
        if (multiple) {
            files = [...files, ...selectedFiles];
        } else {
            files = selectedFiles;
        }
        updatePreviews();
    }

    // 대기 중인 파일 미리보기 URL 업데이트
    function updatePreviews() {
        previewUrls.forEach((url) => URL.revokeObjectURL(url));
        previewUrls = files.map((file) => URL.createObjectURL(file));
    }

    // 대기 중인 파일 삭제
    function removeSelected(index) {
        files = files.filter((_, i) => i !== index);
        updatePreviews();
    }

    // 이미 업로드된 파일 삭제
    function removeUploaded(index) {
        uploadedFiles = uploadedFiles.filter((_, i) => i !== index);
    }

    // 서버로 업로드 전송
    async function uploadFiles() {
        if (files.length === 0) return;

        isLoading = true;
        errorMessage = "";

        const formData = new FormData();
        files.forEach((file) => formData.append("files", file));

        fastapi(
            "post",
            "/api/uploadfiles/",
            formData,
            (json) => {
                isLoading = false;
                files = [];
                previewUrls.forEach((url) => URL.revokeObjectURL(url));
                previewUrls = [];

                // 상위 페이지의 리스트와 동기화 (bindable)
                uploadedFiles = [...uploadedFiles, ...json];

                if (onUpload) {
                    onUpload(json);
                }
            },
            (err) => {
                isLoading = false;
                errorMessage = err.detail || "업로드에 실패했습니다.";
            },
        );
    }

    onDestroy(() => {
        previewUrls.forEach((url) => URL.revokeObjectURL(url));
    });
</script>

<div class="uploader-container">
    <!-- 1. 업로드된 파일 목록 (결과) -->
    {#if uploadedFiles.length > 0}
        <div class="uploaded-section mb-4">
            <h6 class="text-muted mb-2 small">
                첨부된 파일 ({uploadedFiles.length})
            </h6>
            <div class="preview-grid mb-3 pb-3 border-bottom">
                {#each uploadedFiles as img, i}
                    <div class="preview-item">
                        {#if img.thumbnail_filename}
                            <img
                                src={`${PUBLIC_SERVER_URL}/uploads/thumbnails/${img.thumbnail_filename}`}
                                alt={img.original_name}
                            />
                        {:else}
                            <div class="doc-preview">
                                <span class="doc-icon">📄</span>
                                <span class="doc-name">{img.original_name}</span
                                >
                            </div>
                        {/if}
                        <button
                            type="button"
                            class="delete-btn"
                            onclick={() => removeUploaded(i)}
                            title="삭제">&times;</button
                        >
                        {#if img.thumbnail_filename && onInsert}
                            <button
                                type="button"
                                class="insert-btn"
                                onclick={() =>
                                    onInsert(
                                        `${PUBLIC_SERVER_URL}/uploads/${img.filename}`,
                                    )}
                                title="본문에 삽입"
                            >
                                <span style="font-size: 12px;">📥 삽입</span>
                            </button>
                        {/if}
                    </div>
                {/each}
            </div>
        </div>
    {/if}

    <!-- 2. 파일 선택 및 업로드 버튼 -->
    <div class="input-group">
        <label class="file-label">
            <span class="btn btn-secondary">파일 선택</span>
            <input
                type="file"
                accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt"
                {multiple}
                onchange={handleFileChange}
                class="hidden-input"
            />
        </label>

        {#if files.length > 0}
            <button
                type="button"
                class="btn btn-primary"
                onclick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    uploadFiles();
                }}
                disabled={isLoading}
            >
                {#if isLoading}업로드 중...{:else}서버로 전송 ({files.length}){/if}
            </button>
        {/if}
    </div>

    {#if errorMessage}
        <p class="error-text">{errorMessage}</p>
    {/if}

    <!-- 3. 선택 대기 중인 파일 미리보기 -->
    {#if files.length > 0}
        <div class="pending-section mt-3">
            <p class="small text-primary mb-2">업로드 대기 중...</p>
            <div class="preview-grid">
                {#each files as file, i}
                    <div class="preview-item pending">
                        {#if file.type.startsWith("image/")}
                            <img src={previewUrls[i]} alt="pending" />
                        {:else}
                            <div class="doc-preview">
                                <span class="doc-icon">📄</span>
                                <span class="doc-name">{file.name}</span>
                            </div>
                        {/if}
                        <button
                            type="button"
                            class="delete-btn"
                            onclick={() => removeSelected(i)}>&times;</button
                        >
                    </div>
                {/each}
            </div>
        </div>
    {/if}
</div>

<style>
    .uploader-container {
        border: 2px dashed #ddd;
        padding: 20px;
        border-radius: 8px;
        background: #fdfdfd;
        transition: border-color 0.3s;
    }

    .uploader-container:hover {
        border-color: #aaa;
    }

    .input-group {
        display: flex;
        gap: 10px;
        justify-content: center;
        align-items: center;
        margin-bottom: 20px;
    }

    .hidden-input {
        display: none;
    }

    .btn {
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 600;
        transition: opacity 0.2s;
        border: none;
    }

    .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .btn-primary {
        background-color: #007bff;
        color: white;
    }

    .btn-secondary {
        background-color: #6c757d;
        color: white;
    }

    .preview-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
        gap: 15px;
    }

    .preview-item {
        position: relative;
        aspect-ratio: 1;
        border-radius: 6px;
        overflow: hidden;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
    }

    .preview-item img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }

    .doc-preview {
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        background: #f8f9fa;
        padding: 5px;
        text-align: center;
    }

    .doc-icon {
        font-size: 2rem;
    }

    .doc-name {
        font-size: 0.7rem;
        word-break: break-all;
        margin-top: 5px;
        color: #666;
    }

    .delete-btn {
        position: absolute;
        top: 5px;
        right: 5px;
        background: rgba(255, 0, 0, 0.7);
        color: white;
        border: none;
        border-radius: 50%;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
    }

    .delete-btn:hover {
        background: rgba(255, 0, 0, 1);
    }

    .insert-btn {
        position: absolute;
        bottom: 5px;
        left: 5px;
        right: 5px;
        background: rgba(0, 123, 255, 0.8);
        color: white;
        border: none;
        border-radius: 4px;
        padding: 2px 4px;
        cursor: pointer;
        opacity: 0;
        transition: opacity 0.2s;
    }

    .preview-item:hover .insert-btn {
        opacity: 1;
    }

    .insert-btn:hover {
        background: rgba(0, 123, 255, 1);
    }

    .error-text {
        color: #dc3545;
        font-size: 0.9em;
        margin-bottom: 15px;
    }
</style>
