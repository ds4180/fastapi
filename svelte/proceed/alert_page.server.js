import { fail } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch }) {
    const [alertRes, userRes] = await Promise.all([
        fetch(`${env.SERVER_URL}/api/alert/list`),
        fetch(`${env.SERVER_URL}/api/users/list`)
    ]);

    let alerts = [];
    let users = [];

    if (alertRes.ok) alerts = await alertRes.json();
    if (userRes.ok) {
        const userData = await userRes.json();
        users = userData.users || [];
    }

    return { alerts, users };
}

/** @type {import('./$types').Actions} */
export const actions = {
    create: async ({ request, fetch }) => {
        const formData = await request.formData();

        // 날짜 데이터 처리 (비어있으면 null)
        const startDate = formData.get('start_date');
        const endDate = formData.get('end_date');

        const data = {
            message: formData.get('message'),
            level: parseInt(formData.get('level')),
            style: formData.get('style'),
            position: formData.get('position') || "top",
            route: formData.get('route') || null,
            redirect_url: formData.get('redirect_url') || null,
            reset_sec: parseInt(formData.get('reset_sec') || '5'),
            confirm_text: formData.get('confirm_text') || '확인하였습니다',
            start_date: startDate ? new Date(startDate).toISOString() : null,
            end_date: endDate ? new Date(endDate).toISOString() : null,
            target_users: formData.get('target_users') || null
        };

        const response = await fetch(`${env.SERVER_URL}/api/alert/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            return { success: true };
        }

        const error = await response.json().catch(() => ({ detail: "알 수 없는 에러" }));
        return fail(response.status, { error, message: data.message });
    },

    toggle: async ({ request, fetch }) => {
        const formData = await request.formData();
        const id = formData.get('id');
        const response = await fetch(`${env.SERVER_URL}/api/alert/toggle/${id}`, { method: 'POST' });
        if (response.ok) return { success: true };
        return fail(response.status);
    },

    delete: async ({ request, fetch }) => {
        const formData = await request.formData();
        const id = formData.get('id');
        const response = await fetch(`${env.SERVER_URL}/api/alert/delete/${id}`, { method: 'DELETE' });
        if (response.ok) return { success: true };
        return fail(response.status);
    }
};
