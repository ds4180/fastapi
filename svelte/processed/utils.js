/**
 * 날짜 포맷팅 (YYYY-MM-DD)
 * @param {string} dateString - 'YYYY-MM-DD' 형태의 문자열
 * @returns {string} - 예: '2024-02-14'
 */
export function formatDate(dateString) {
    if (!dateString) return '';
    return dateString; // 이미 YYYY-MM-DD로 오므로 그대로 반환 (필요시 추가 가공)
}

/**
 * 일시 포맷팅 (YYYY-MM-DD HH:mm)
 * @param {string} dateTimeString - ISO 포맷 문자열
 * @returns {string} - 예: '2024-02-14 14:30'
 */
export function formatDateTime(dateTimeString) {
    if (!dateTimeString) return '';
    const date = new Date(dateTimeString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

/**
 * 시간(분 단위 정수)을 '시간:분' 형식으로 변환
 * @param {number} minutes - 분 단위 정수
 * @returns {string} - 예: '1시간 30분'
 */
export function formatDuration(minutes) {
    if (minutes === null || minutes === undefined) return '';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    if (h > 0) {
        return `${h}시간 ${m}분`;
    } else {
        return `${m}분`;
    }
}
