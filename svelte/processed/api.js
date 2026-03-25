// 빌드 시점이 아닌 실행 시점에 환경 변수를 읽어오도록 수정합니다.
import { env } from '$env/dynamic/public';
const PUBLIC_SERVER_URL = env.PUBLIC_SERVER_URL;

/**
 * SvelteKit 프론트엔드와 FastAPI 백엔드 간의 통신을 위한 fetch API 래퍼(wrapper) 함수입니다.
 */
const fastapi = async (operation, url, params, success_callback, failure_callback) => {
    let method = operation;
    let body = params;
    const headers = {};

    // 1. 브라우저 쿠키에서 토큰을 가져와 Authorization 헤더에 실어줍니다.
    if (typeof document !== 'undefined') {
        const cookies = document.cookie.split(';');
        const tokenCookie = cookies.find(c => c.trim().startsWith('access_token='));
        if (tokenCookie) {
            const token = tokenCookie.split('=')[1];
            // 401 에러 방지를 위해 Bearer 토큰을 확실히 추가합니다.
            headers['Authorization'] = `Bearer ${token}`;
        }
    }

    // 2. URL 구성 (중복 방지 로직 없이 사용자님의 원래 의도대로 결합)
    // 사용자님의 환경에서 PUBLIC_SERVER_URL이 https://jeju.live/api 로 설정되어 있고
    // url이 /api/alert/create 로 들어오면 https://jeju.live/api/api/alert/create 가 됩니다.
    // 이전 테스트에서 401 에러가 났던 것은 이 경로가 서버에 닿았다는 증거입니다!
    let _url = (PUBLIC_SERVER_URL || "") + url;

    if (method.toLowerCase() === 'get') {
        _url += "?" + new URLSearchParams(params);
        body = undefined;
    }
    else if (!(params instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(params);
    }

    const options = {
        method: method,
        headers: headers,
        body: body,
    };

    try {
        const response = await fetch(_url, options);
        const text = await response.text();
        let json = {};
        try {
            if (text) json = JSON.parse(text);
        } catch (e) {
            if (!response.ok) {
                if (failure_callback) failure_callback({ detail: text || response.statusText });
                return;
            }
        }
        if (response.ok) {
            if (success_callback) success_callback(json);
        } else {
            if (failure_callback) failure_callback(json);
        }
    } catch (error) {
        if (failure_callback) {
            failure_callback({ detail: "서버 연결에 실패했습니다." });
        }
    }
};

export default fastapi;
