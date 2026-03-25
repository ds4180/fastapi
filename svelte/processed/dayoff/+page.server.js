
import { fail, redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, cookies }) {
    const accessToken = cookies.get('access_token');

    // 토큰 없으면 로그인 페이지로 리다이렉트
    if (!accessToken) {
        throw redirect(303, '/user-login');
    }

    // 서버로 요청을 보낼 때 인증 헤더 추가
    const headers = {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
    };

    try {
        // 백엔드 API 호출: 내 휴무일 목록 조회
        const response = await fetch(`${env.SERVER_URL}/api/dayoff/list?skip=0&limit=100`, {
            headers
        });

        if (response.ok) {
            const result = await response.json();
            return {
                dayoff_list: result.data || [],
                total: result.total || 0
            };
        } else {
            // 토큰 만료 등의 이유로 실패 시 로그인 페이지로 리다이렉트 처리 고려
            if (response.status === 401) {
                cookies.delete('access_token', { path: '/' });
                cookies.delete('username', { path: '/' });
                throw redirect(303, '/user-login');
            }
            // 그 외 에러는 일단 빈 리스트 반환하거나 에러 처리
            console.error("Failed to load dayoff list:", response.status);
            return { dayoff_list: [], total: 0, error: '데이터를 불러오는데 실패했습니다.' };
        }
    } catch (error) {
        console.error("DayOff load error:", error);
        // 리다이렉트 예외는 다시 던져야 SvelteKit이 처리함
        if (error.status === 303) throw error;
        return { dayoff_list: [], total: 0, error: '서버 연결 실패' };
    }
}

/** @type {import('./$types').Actions} */
export const actions = {
    // 휴무일 생성
    create: async ({ request, fetch, cookies }) => {
        const accessToken = cookies.get('access_token');
        if (!accessToken) {
            throw redirect(303, '/user-login');
        }

        const formData = await request.formData();
        const datesJson = formData.get('dates');
        const type = formData.get('type');
        const memo = formData.get('memo');

        let dates = [];
        try {
            dates = JSON.parse(datesJson);
        } catch (e) {
            return fail(400, { error: '잘못된 날짜 형식입니다.', dates: datesJson, type, memo });
        }

        if (!dates || dates.length === 0) {
            return fail(400, { error: '날짜를 선택해주세요.', dates: datesJson, type, memo });
        }

        try {
            const response = await fetch(`${env.SERVER_URL}/api/dayoff/create`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    type,
                    dates,
                    memo
                })
            });

            if (!response.ok) {
                const err = await response.json();
                return fail(response.status, { error: err.detail || '저장에 실패했습니다.', type, memo });
            }

            // 성공 시 리다이렉트하지 않고 그대로 있으면 load 함수가 다시 실행되어 목록이 갱신됨
            return { success: true };

        } catch (error) {
            console.error("DayOff create error:", error);
            return fail(500, { error: '서버 에러가 발생했습니다.', type, memo });
        }
    },

    // 휴무일 삭제 (취소)
    delete: async ({ request, fetch, cookies }) => {
        const accessToken = cookies.get('access_token');
        if (!accessToken) {
            throw redirect(303, '/user-login');
        }

        const formData = await request.formData();
        const dayoff_id = formData.get('dayoff_id');

        try {
            const response = await fetch(`${env.SERVER_URL}/api/dayoff/delete/${dayoff_id}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            });

            if (!response.ok) {
                // const err = await response.json(); // DELETE 응답에 body 없을수도 있음
                return fail(response.status, { error: '삭제에 실패했습니다.' });
            }

            return { success: true };
        } catch (error) {
            console.error("DayOff delete error:", error);
            return fail(500, { error: '서버 에러가 발생했습니다.' });
        }
    }
};
