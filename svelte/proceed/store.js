// svelte/store에서 writable 함수를 가져옵니다.
// writable은 값이 변경될 수 있는 '스토어(store)'를 생성하는 함수입니다.
// 스토어는 애플리케이션의 여러 컴포넌트에서 공유하고 반응적으로 사용할 수 있는 값의 저장소입니다.
import { writable } from 'svelte/store';

// $app/environment에서 browser 변수를 가져옵니다.
// 이 변수는 코드가 브라우저 환경에서 실행 중인지(true) 서버 환경에서 실행 중인지(false) 알려줍니다.
// window나 sessionStorage 같은 브라우저 전용 API는 서버에 존재하지 않으므로,
// 이 변수를 사용하여 서버 사이드 렌더링(SSR) 중 에러가 발생하는 것을 방지합니다.
import { browser } from '$app/environment';

// sessionStorage에 데이터를 저장할 때 사용할 키(key)를 상수로 정의합니다.
// 상수를 사용하면 오타를 방지하고 유지보수를 쉽게 할 수 있습니다.
const PAGE_KEY = 'last_viewed_page';
const KW_KEY = 'last_search_keyword';

// 페이지 스토어
const initialPage = browser ? window.sessionStorage.getItem(PAGE_KEY) ?? 0 : 0;
export const lastViewedPage = writable(Number(initialPage));

// 검색어 스토어
const initialKeyword = browser ? window.sessionStorage.getItem(KW_KEY) ?? "" : "";
export const keyword = writable(initialKeyword);

if (browser) {
    lastViewedPage.subscribe((value) => {
        window.sessionStorage.setItem(PAGE_KEY, value);
    });

    keyword.subscribe((value) => {
        window.sessionStorage.setItem(KW_KEY, value);
    });
}

/** 
 * 현재 화면에 표시되어야 할 알림 대기열입니다.
 * @type {import('svelte/store').Writable<Array<Object>>} 
 */
export const alerts = writable([]);

/** 
 * '다시 보지 않기'를 클릭한 알림 ID 목록입니다.
 * 모든 Alert 컴포넌트 인스턴스가 동기화되도록 별도 스토어로 관리합니다.
 */
const initialDismissed = browser ? JSON.parse(window.localStorage.getItem("dismissed_alerts") || "{}") : {};
export const dismissedIds = writable(initialDismissed);

/**
 * 이번 세션(새로고침 전) 동안만 숨길 알림 ID 목록입니다.
 * 확인 버튼을 누르거나 자동 소멸된 알림이 폴링 시 다시 살아나는 것을 방지합니다.
 */
export const sessionHiddenIds = writable(new Set());

/**
 * 알림 휴게소 (Quiet Mode) 상태입니다.
 * true일 경우 Lv.1~3 알림이 화면에 나타나지 않습니다.
 */
const initialQuiet = browser ? localStorage.getItem("is_quiet_mode") === "true" : false;
export const isQuietMode = writable(initialQuiet);

if (browser) {
    isQuietMode.subscribe(value => {
        localStorage.setItem("is_quiet_mode", value);
    });
    dismissedIds.subscribe((value) => {
        window.localStorage.setItem("dismissed_alerts", JSON.stringify(value));
    });
}

/**
 * 프로젝트 전역 알림 및 업무 지시 송신 도구입니다.
 * 어디서든 notify.send()를 통해 직원에게 지시를 내릴 수 있습니다.
 */
export const notify = {
    /**
     * @param {string} msg - 알림 본문 (2~3줄의 핵심 지시)
     * @param {Object} [options] - 추가 옵션
     * @param {number} [options.level=1] - 강도 (1:토스트, 2:배너, 3:일반확인, 4:인과응보리셋)
     * @param {string} [options.style='info'] - 색상 스타일 (info, success, warning, danger)
     * @param {string} [options.route] - 특정 페이지 노출용 (비어있으면 전역)
     * @param {string} [options.redirect_url] - 확인 버튼 클릭 시 강제 이동할 주소
     * @param {number} [options.resetSec=0] - Level 4 사용 시 리셋 타이머 초
     * @param {string} [options.confirmText='확인하였습니다'] - 버튼 문구
     */
    send: (msg, options = {}) => {
        alerts.update(all => [...all, {
            id: options.id || Math.random().toString(36).substring(2, 9),
            message: msg,
            level: options.level || 1,
            style: options.style || 'info',
            route: options.route || null,
            redirect_url: options.redirect_url || null,
            resetSec: options.resetSec || 0,
            confirmText: options.confirmText || '확인하였습니다',
            createdAt: Date.now()
        }]);
    },

    /** 
     * 특정 알림을 대기열에서 제거하고, 이번 세션 동안 다시 나타나지 않게 기록합니다.
     * @param {string} id - 삭제할 알림의 고유 ID
     */
    dismiss: (id) => {
        sessionHiddenIds.update(prev => {
            prev.add(id);
            return prev;
        });
        alerts.update(all => all.filter(a => a.id !== id));
    }
};

