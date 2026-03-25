/** @type {import('./$types').LayoutServerLoad} */
export function load({ cookies }) {
    // 가장 직관적인 방법: 쿠키에서 username 만 꺼내서 전달합니다.
    const username = cookies.get('username') || "";

    return {
        username
    };
}