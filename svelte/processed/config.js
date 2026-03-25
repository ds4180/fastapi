export const config = {
    siteName: 'Pybo',
    siteDescription: 'A premium community platform for developers and enthusiasts.',
    version: '1.0.0',
    apiBaseUrl: import.meta.env.VITE_API_SERVER || 'http://127.0.0.1:8000',
    theme: {
        primaryColor: '#6366f1',
        secondaryColor: '#a855f7',
    },
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
