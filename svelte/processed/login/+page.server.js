import { fail, redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/** @type {import('./$types').PageServerLoad} */
export function load() {
    return {};
}

/** @type {import('./$types').Actions} */
export const actions = {
    default: async ({ request, fetch, cookies }) => {
        const formData = await request.formData();
        const username = formData.get('username');
        const password = formData.get('password');

        const body = new URLSearchParams();
        body.append('username', username);
        body.append('password', password);

        const userAgent = request.headers.get('user-agent') || '';
        const isMobile = /Mobi|Android|iPhone|iPad/i.test(userAgent);
        const deviceCategory = isMobile ? 'MOBILE' : 'WORKSPACE';

        const loginUrl = `${env.SERVER_URL}/users/login?device_category=${deviceCategory}`;

        // 1. fetch 요청
        let response;
        try {
            response = await fetch(loginUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body,
            });
        } catch (err) {
            // 서버 전송 자체가 실패한 경우 (서버 꺼짐 등)
            return fail(500, {
                error: { detail: '로그인 서버에 연결할 수 없습니다.' },
                username,
            });
        }

        // 2. 응답 분석 (401 오류 등 처리)
        if (!response.ok) {
            let errorData;
            try {
                errorData = await response.json();
            } catch (e) {
                // 백엔드가 JSON을 주지 않는 특수한 경우
                errorData = { detail: '로그인 정보를 확인해주세요.' };
            }
            return fail(response.status, {
                error: errorData,
                username,
            });
        }

        // 3. 로그인 성공 처리
        const result = await response.json();
        cookies.set('access_token', result.access_token, { path: '/', httpOnly: true, maxAge: 60 * 60 });
        cookies.set('refresh_token', result.refresh_token, { path: '/', httpOnly: true, maxAge: 60 * 60 * 24 * 3 });
        cookies.set('username', result.username, { path: '/', httpOnly: true, maxAge: 60 * 60 * 24 * 3 });

        throw redirect(303, '/');
    },
};
