import { fastApi } from './api';

/**
 * [v1.9 표준 준수] 관리자 전용 API 모듈
 * 모든 주소 앞에 /api 접두사를 명시합니다.
 */

/**
 * [관리자] 모든 사용자의 휴무 신청 내역 가져오기
 * @returns {Promise<any[]>}
 */
export const adminGetAllDayoffs = () => fastApi('GET', '/api/v1/admin/dayoffs');

/**
 * [관리자] 휴무 신청 상태 업데이트 (승인/반려 등)
 */
export const adminUpdateDayoffStatus = (dayoffId, status) => {
    return fastApi('PUT', `/api/v1/admin/dayoffs/${dayoffId}/status`, { status });
};

/**
 * [v1.5] 앱 엔진 관리 API
 */
export const adminGetApps = () => fastApi('GET', '/api/v1/admin/apps');
export const adminGetAppDetail = (appId) => fastApi('GET', `/api/v1/admin/apps/${appId}`);
export const adminCreateApp = (appData) => fastApi('POST', '/api/v1/admin/apps', appData);
export const adminUpdateApp = (appId, appData) => fastApi('PATCH', `/api/v1/admin/apps/${appId}`, appData);
export const adminDeleteApp = (appId) => fastApi('DELETE', `/api/v1/admin/apps/${appId}`);

/**
 * [v1.5] 메뉴 관리 API
 */
export const adminGetMenus = () => fastApi('GET', '/api/v1/admin/menu');
export const adminCreateMenu = (menuData) => fastApi('POST', '/api/v1/admin/menu', menuData);
export const adminUpdateMenu = (menuId, menuData) => fastApi('PUT', `/api/v1/admin/menu/${menuId}`, menuData);
export const adminDeleteMenu = (menuId) => fastApi('DELETE', `/api/v1/admin/menu/${menuId}`);

/**
 * [v1.5.12] 게시판 인스턴스(BoardConfig) 관리 API
 */
export const adminGetBoards = () => fastApi('GET', '/api/v1/admin/boards');
export const adminCreateBoard = (data) => fastApi('POST', '/api/v1/admin/boards', data);
export const adminUpdateBoard = (id, data) => fastApi('PUT', `/api/v1/admin/boards/${id}`, data);
export const adminDeleteBoard = (id) => fastApi('DELETE', `/api/v1/admin/boards/${id}`);

/**
 * [v1.5.11] 서비스 레지스트리 및 엔진 관리 API
 */
export const adminGetServiceRegistries = () => fastApi('GET', '/api/v1/admin/service-registries');
export const adminCreateServiceRegistry = (data) => fastApi('POST', '/api/v1/admin/service-registries', data);
export const adminDeleteServiceRegistry = (id) => fastApi('DELETE', `/api/v1/admin/service-registries/${id}`);

export const adminGetServiceEngines = () => fastApi('GET', '/api/v1/admin/service-engines');
export const adminCreateServiceEngine = (data) => fastApi('POST', '/api/v1/admin/service-engines', data);
export const adminDeleteServiceEngine = (id) => fastApi('DELETE', `/api/v1/admin/service-engines/${id}`);

export const adminGetServiceBindings = (appId, instanceId) => fastApi('GET', `/api/v1/admin/service-bindings/${appId}/${instanceId}`);
export const adminCreateServiceBinding = (data) => fastApi('POST', '/api/v1/admin/service-bindings', data);
export const adminDeleteServiceBinding = (id) => fastApi('DELETE', `/api/v1/admin/service-bindings/${id}`);
