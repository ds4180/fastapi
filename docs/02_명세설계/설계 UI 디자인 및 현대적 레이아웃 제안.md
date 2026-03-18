# 현대적 디자인 제안 (Proposed Modern Design)

이 문서는 프로젝트의 기능 구현 완료 후 적용을 검토하기 위해 작성된 디자인 가이드입니다.

## 1. 전역 스타일 (`src/app.css`)
프리미엄 다크 모드와 Glassmorphism 효과를 위한 CSS 변수 및 유틸리티입니다.

```css
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');

:root {
    --primary-hsl: 250, 84%, 63%;
    --primary: hsl(var(--primary-hsl));
    --bg-main: #0f172a;
    --bg-card: rgba(30, 41, 59, 0.7);
    --text-main: #f8fafc;
    --border-glass: rgba(255, 255, 255, 0.1);
    --radius-xl: 1.5rem;
}

body {
    font-family: 'Outfit', sans-serif;
    background: radial-gradient(circle at top left, #1e1b4b, #0f172a 50%, #020617);
    color: var(--text-main);
}

.glass-card {
    background: var(--bg-card);
    backdrop-filter: blur(16px);
    border: 1px solid var(--border-glass);
    border-radius: var(--radius-xl);
}
```

## 2. 전역 설정 (`src/lib/config.js`)
내비게이션 및 사이트 메타데이터 관리용 파일입니다.

```javascript
export const config = {
    siteName: 'Pybo',
    navigation: [
        { name: '질문목록', path: '/question_list' },
        { name: '질문 작성', path: '/question-create' },
        { name: '달력', path: '/calendar' },
        { name: '파일', path: '/uploadfiles' },
        { name: '결근계', path: '/day_off' },
        { name: '차트', path: '/chart_view' },
        { name: '배차', path: '/test-dnd3' },
        { name: '노선', path: '/test-svg4' },
    ]
};
```

## 3. 레이아웃 구조 (`src/routes/+layout.svelte`)
스크롤 애니메이션과 현대적인 내비게이션바가 적용된 레이아웃 예시입니다.

- `fixed-top` 내비게이션바 적용
- 스크롤 상태(`isScrolled`)에 따른 투명도 조절
- `animate-fade-in` 효과 적용

---
*참고: 위 디자인은 현재 개발 편의를 위해 제거되었으며, 필요 시 위 코드를 참고하여 다시 복구할 수 있습니다.*
