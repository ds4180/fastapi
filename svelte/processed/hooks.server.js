import { redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * @type {import('@sveltejs/kit').HandleFetch}
 * SvelteKit의 서버 측(load, actions)에서 `fetch` 함수가 호출될 때마다 이 hook이 가로채서 실행됩니다.
 * 이 hook을 사용하여 API 요청에 인증 헤더를 자동으로 추가하고, 토큰 만료 시 재발급하는 로직을 중앙에서 관리할 수 있습니다.
 */
export async function handleFetch({ request, fetch, event }) {
    // 1. FastAPI 백엔드로 향하는 모든 요청에 access_token을 담은 Authorization 헤더를 추가합니다.
    //    - `event.cookies`에서 access_token을 가져옵니다.
    //    - 요청 URL이 `env.SERVER_URL`로 시작하는 경우에만 헤더를 추가하여, 외부 API 요청에는 토큰이 전송되지 않도록 합니다.
    const access_token = event.cookies.get('access_token');
    if (access_token && request.url.startsWith(env.SERVER_URL)) {
        request.headers.set('Authorization', `Bearer ${access_token}`);
    }

    // 2. 수정된 헤더를 포함하여 원래 요청을 보냅니다.
    let response = await fetch(request);

    // 3. API 요청이 실패하고, 그 원인이 '액세스 토큰 만료'(401 Unauthorized)인 경우 토큰 재발급을 시도합니다.
    // 단, 로그인 요청(/api/users/login) 자체의 401 에러는 토큰 만료가 아닌 인증 실패이므로 제외합니다.
    if (response.status === 401 && request.url.startsWith(env.SERVER_URL) && !request.url.includes('/api/users/login')) {
        // 3-1. 재발급에 필요한 refresh_token을 쿠키에서 가져옵니다.
        const refresh_token = event.cookies.get('refresh_token');
        const cookieOptions = { path: '/', httpOnly: true, secure: false, sameSite: 'lax' };

        // 3-2. refresh_token이 없으면, 사용자를 완전히 로그아웃 처리하고 로그인 페이지로 리디렉션합니다.
        if (!refresh_token) {
            event.cookies.delete('access_token', cookieOptions);
            event.cookies.delete('refresh_token', cookieOptions);
            event.cookies.delete('username', cookieOptions);
            throw redirect(303, '/user-login');
        }

        // 3-3. refresh_token으로 새로운 access_token을 요청하는 API를 호출합니다.
        const refresh_response = await fetch(`${env.SERVER_URL}/api/users/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refresh_token })
        });

        // 3-4. 토큰 재발급에 성공한 경우
        if (refresh_response.ok) {
            const { access_token: new_access_token } = await refresh_response.json();

            // 새로 발급받은 access_token을 쿠키에 저장합니다.
            event.cookies.set('access_token', new_access_token, {
                ...cookieOptions,
                maxAge: 60 * 15 // 15분
            });

            // 원래 요청의 Authorization 헤더를 새로운 토큰으로 교체한 후, 요청을 재시도합니다.
            // 이 과정을 통해 클라이언트는 토큰 만료 사실을 인지하지 못한 채 자연스럽게 API 통신을 이어갈 수 있습니다.
            request.headers.set('Authorization', `Bearer ${new_access_token}`);
            response = await fetch(request);
        } else {
            // 3-5. 토큰 재발급에 실패한 경우 (refresh_token도 만료되었거나 유효하지 않음)
            // 모든 인증 관련 쿠키를 삭제하고 사용자를 로그인 페이지로 리디렉션합니다.
            event.cookies.delete('access_token', cookieOptions);
            event.cookies.delete('refresh_token', cookieOptions);
            event.cookies.delete('username', cookieOptions);
            throw redirect(303, '/user-login');
        }
    }

    // 4. 최종 응답(최초 성공, 재시도 후 성공, 또는 재발급 실패 외의 다른 실패)을 원래 `fetch`를 호출했던 곳으로 반환합니다.
    return response;
}
