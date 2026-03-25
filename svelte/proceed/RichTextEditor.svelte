<script>
    import { onMount, onDestroy } from "svelte";
    import { Editor } from "@tiptap/core";
    import StarterKit from "@tiptap/starter-kit";
    import Placeholder from "@tiptap/extension-placeholder";
    import TextAlign from "@tiptap/extension-text-align";
    import Image from "@tiptap/extension-image";
    import Highlight from "@tiptap/extension-highlight";
    import TextStyle from "@tiptap/extension-text-style";
    import Underline from "@tiptap/extension-underline";
    import Link from "@tiptap/extension-link";
    import Icon from "@iconify/svelte";

    let { content = $bindable(""), editorInstance = $bindable(null) } =
        $props();

    let element;
    let editor = $state(null);

    onMount(() => {
        editor = new Editor({
            element: element,
            extensions: [
                StarterKit,
                Underline,
                Placeholder.configure({
                    placeholder: "여기에 내용을 입력하세요...",
                }),
                TextAlign.configure({
                    types: ["heading", "paragraph"],
                }),
                Link.configure({
                    openOnClick: false,
                    HTMLAttributes: {
                        target: "_blank",
                    },
                }),
                Image.configure({
                    HTMLAttributes: {
                        class: "img-fluid rounded shadow-sm my-3",
                    },
                }),
                Highlight,
                TextStyle,
            ],
            content: content,
            onUpdate: ({ editor }) => {
                content = editor.getHTML();
            },
            onCreate: ({ editor: e }) => {
                editorInstance = e; // 부모에서 제어할 수 있도록 인스턴스 전발
            },
        });
    });

    onDestroy(() => {
        if (editor) {
            editor.destroy();
        }
    });

    // 헬퍼 함수들
    const toggleBold = () => editor.chain().focus().toggleBold().run();
    const toggleItalic = () => editor.chain().focus().toggleItalic().run();
    const toggleUnderline = () =>
        editor.chain().focus().toggleUnderline().run();
    const toggleStrike = () => editor.chain().focus().toggleStrike().run();
    const toggleHeading = (level) =>
        editor.chain().focus().toggleHeading({ level }).run();
    const toggleBulletList = () =>
        editor.chain().focus().toggleBulletList().run();
    const toggleOrderedList = () =>
        editor.chain().focus().toggleOrderedList().run();
    const toggleBlockquote = () =>
        editor.chain().focus().toggleBlockquote().run();
    const toggleCodeBlock = () =>
        editor.chain().focus().toggleCodeBlock().run();
    const undo = () => editor.chain().focus().undo().run();
    const redo = () => editor.chain().focus().redo().run();
</script>

<div class="rich-editor">
    {#if editor}
        <div class="toolbar">
            <div class="btn-group">
                <button
                    type="button"
                    onclick={toggleBold}
                    class:active={editor.isActive("bold")}
                    title="굵게"
                >
                    <Icon icon="lucide:bold" />
                </button>
                <button
                    type="button"
                    onclick={toggleItalic}
                    class:active={editor.isActive("italic")}
                    title="기울임"
                >
                    <Icon icon="lucide:italic" />
                </button>
                <button
                    type="button"
                    onclick={toggleUnderline}
                    class:active={editor.isActive("underline")}
                    title="밑줄"
                >
                    <Icon icon="lucide:underline" />
                </button>
                <button
                    type="button"
                    onclick={toggleStrike}
                    class:active={editor.isActive("strike")}
                    title="취소선"
                >
                    <Icon icon="lucide:strikethrough" />
                </button>
            </div>

            <div class="divider"></div>

            <div class="btn-group">
                <button
                    type="button"
                    onclick={() => toggleHeading(1)}
                    class:active={editor.isActive("heading", { level: 1 })}
                    title="제목 1"
                >
                    <Icon icon="lucide:heading-1" />
                </button>
                <button
                    type="button"
                    onclick={() => toggleHeading(2)}
                    class:active={editor.isActive("heading", { level: 2 })}
                    title="제목 2"
                >
                    <Icon icon="lucide:heading-2" />
                </button>
                <button
                    type="button"
                    onclick={() => toggleHeading(3)}
                    class:active={editor.isActive("heading", { level: 3 })}
                    title="제목 3"
                >
                    <Icon icon="lucide:heading-3" />
                </button>
            </div>

            <div class="divider"></div>

            <div class="btn-group">
                <button
                    type="button"
                    onclick={toggleBulletList}
                    class:active={editor.isActive("bulletList")}
                    title="글머리 기호"
                >
                    <Icon icon="lucide:list" />
                </button>
                <button
                    type="button"
                    onclick={toggleOrderedList}
                    class:active={editor.isActive("orderedList")}
                    title="번호 매기기"
                >
                    <Icon icon="lucide:list-ordered" />
                </button>
                <button
                    type="button"
                    onclick={toggleBlockquote}
                    class:active={editor.isActive("blockquote")}
                    title="인용구"
                >
                    <Icon icon="lucide:quote" />
                </button>
                <button
                    type="button"
                    onclick={toggleCodeBlock}
                    class:active={editor.isActive("codeBlock")}
                    title="코드 블록"
                >
                    <Icon icon="lucide:file-code" />
                </button>
            </div>

            <div class="divider"></div>

            <div class="btn-group ms-auto">
                <button type="button" onclick={undo} title="실행 취소">
                    <Icon icon="lucide:undo" />
                </button>
                <button type="button" onclick={redo} title="다시 실행">
                    <Icon icon="lucide:redo" />
                </button>
            </div>
        </div>
    {/if}

    <div class="editor-content" bind:this={element}></div>
</div>

<style>
    .rich-editor {
        border: 1px solid #dee2e6;
        border-radius: 0.375rem;
        background: white;
        overflow: hidden;
    }

    .toolbar {
        display: flex;
        flex-wrap: wrap;
        gap: 0.25rem;
        padding: 0.5rem;
        background: #f8f9fa;
        border-bottom: 1px solid #dee2e6;
        align-items: center;
    }

    .btn-group {
        display: flex;
        gap: 2px;
    }

    .divider {
        width: 1px;
        height: 1.5rem;
        background: #dee2e6;
        margin: 0 0.25rem;
    }

    button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2rem;
        height: 2rem;
        border: 1px solid transparent;
        border-radius: 0.25rem;
        background: transparent;
        color: #495057;
        cursor: pointer;
        transition: all 0.2s;
    }

    button:hover {
        background: #e9ecef;
        color: #212529;
    }

    button.active {
        background: #e7f1ff;
        color: #0d6efd;
        border-color: #9ec5fe;
    }

    .editor-content {
        padding: 1rem;
        min-height: 300px;
        max-height: 600px;
        overflow-y: auto;
    }

    /* TipTap 내부 스타일 보정 */
    :global(.ProseMirror) {
        outline: none;
        min-height: 280px;
    }

    :global(.ProseMirror p.is-editor-empty:first-child::before) {
        content: attr(data-placeholder);
        float: left;
        color: #adb5bd;
        pointer-events: none;
        height: 0;
    }

    :global(.ProseMirror blockquote) {
        padding-left: 1rem;
        border-left: 3px solid #dee2e6;
        color: #6c757d;
        font-style: italic;
    }

    :global(.ProseMirror pre) {
        background: #212529;
        color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.375rem;
        font-family: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
            "Courier New", monospace;
    }
</style>
