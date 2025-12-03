<script>
  import { onMount } from "svelte";

  let ws;
  let editor = null;

  onMount(() => {
    ws = new WebSocket("ws://localhost:8000/ws");

    ws.onopen = () => {
      console.log("WebSocket 연결됨");

      // 알림 권한 요청
      if (Notification.permission === "default") {
        Notification.requestPermission().then(permission => {
          console.log("알림 권한:", permission);
        });
      }
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "edit_status") {
        editor = data.editor;

        // 브라우저 알림
        if (Notification.permission === "granted") {
          new Notification("편집 상태 알림", {
            body: editor ? "누군가 편집 중입니다!" : "편집 가능",
          });
        }

        // 소리 재생
        const audio = new Audio("/sounds/notify.mp3"); // 소리 파일 경로
        audio.play().catch(err => console.log("소리 재생 실패:", err));
      }
    };
  });

  function startEdit() {
    ws.send(JSON.stringify({ action: "start_edit" }));
  }

  function stopEdit() {
    ws.send(JSON.stringify({ action: "stop_edit" }));
  }
</script>

<div>
  {#if editor}
    <p>⚠️ 누군가 편집 중입니다!</p>
  {:else}
    <p>편집 가능</p>
  {/if}

  <button on:click={startEdit}>편집 시작</button>
  <button on:click={stopEdit}>편집 종료</button>
</div>
