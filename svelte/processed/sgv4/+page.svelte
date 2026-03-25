<script>
    import { onMount } from "svelte";

    // ========================================
    // 1. 정거장 정의 (Station Nodes)
    // ========================================
    // 버스 노선도의 각 정거장 위치와 정보를 정의합니다.
    //
    // 좌표 시스템:
    // - x: 좌우 위치 (50 ~ 950) - 300px 증가
    // - y: 상하 위치
    //   * 상단 라인 (y=100): A, B, C, D, E, F 정거장
    //   * 중간 라인 (y=150): G 정거장 (분기점)
    //   * 하단 라인 (y=200): H, I, J, K, L, M 정거장
    //
    // 노선 구조:
    // - 상단: A(제주) → B → C → D → E → F → G(고산)
    // - 하단: G(고산) → H → I → J → K → L → M(등기소)
    let stations = [
        { id: "A", x: 50, y: 100, label: "제주" },
        { id: "B", x: 200, y: 100, label: "오일장" },
        { id: "C", x: 350, y: 100, label: "하귀" },
        { id: "D", x: 500, y: 100, label: "애월" },
        { id: "E", x: 650, y: 100, label: "한림" },
        { id: "F", x: 800, y: 100, label: "신창" },
        { id: "G", x: 950, y: 150, label: "고산" },
        { id: "H", x: 800, y: 200, label: "대정" },
        { id: "I", x: 650, y: 200, label: "화순" },
        { id: "J", x: 500, y: 200, label: "창천" },
        { id: "K", x: 350, y: 200, label: "중문" },
        { id: "L", x: 200, y: 200, label: "신서귀" },
        { id: "M", x: 50, y: 200, label: "등기소" },
    ];

    // 정거장 ID로 빠르게 정거장 정보를 찾기 위한 Map 자료구조
    // 예: stationMap.get("A") → { id: "A", x: 50, y: 100, label: "제주" }
    const stationMap = new Map(stations.map((s) => [s.id, s]));
    // ========================================
    // 2. 경로 정의 (Track Connections)
    // ========================================
    // 정거장 간의 연결선을 정의합니다.
    // SVG에서 선(line)을 그리기 위한 데이터로, 각 배열은 [시작정거장, 종료정거장] 형식입니다.
    //
    // 전체 노선: A → B → C → D → E → F → G → H → I → J → K → L → M
    let tracks = [
        ["A", "B"],
        ["B", "C"],
        ["C", "D"],
        ["D", "E"],
        ["E", "F"],
        ["F", "G"],
        ["G", "H"],
        ["H", "I"],
        ["I", "J"],
        ["J", "K"],
        ["K", "L"],
        ["L", "M"],
    ];

    // ========================================
    // 3. 시간 변환 헬퍼 함수
    // ========================================
    // HHMM 형식(예: 830, 1425)을 자정 이후 분 단위로 변환합니다.
    //
    // 변환 방법:
    // 1. 시간 추출: Math.floor(hhmm / 100) → 830 → 8시간
    // 2. 분 추출: hhmm % 100 → 830 → 30분
    // 3. 총 분 계산: (시간 * 60) + 분 → (8 * 60) + 30 = 510분
    //
    // 예시:
    // - 830 (8:30) → 510분
    // - 1425 (14:25) → 865분
    // - 0 (0:00) → 0분
    // - 2359 (23:59) → 1439분
    function timeToMinutes(hhmm) {
        const hours = Math.floor(hhmm / 100); // 시간 부분 추출
        const minutes = hhmm % 100; // 분 부분 추출
        return hours * 60 + minutes; // 총 분으로 변환
    }

    // ========================================
    // 4. 버스 스케줄 데이터
    // ========================================
    // JSON 파일에서 버스 스케줄 데이터를 import합니다.
    // 전체 32개 로번을 3개 파일로 나누어 저장
    import busDataPart1 from "./bus-202-part1.json"; // 1~10로번
    import busDataPart2 from "./bus-202-part2.json"; // 11~20로번
    import busDataPart3 from "./bus-202-part3.json"; // 21~32로번

    // 정거장 이름 → ID 매핑
    // JSON 파일에 있는 모든 정거장 이름을 매핑해야 합니다
    const stationNameToId = {
        제주: "A",
        오일장: "B",
        하귀: "C",
        애월: "D",
        한림: "E",
        신창: "F",
        고산: "G",
        대정: "H",
        모슬: "H", // 모슬은 대정과 같은 위치
        화순: "I",
        창천: "J",
        중문: "K",
        신서귀: "L",
        서귀: "L", // 서귀는 신서귀와 같은 위치
        등기소: "M",
        // 특수 경유지들 - 가장 가까운 정거장으로 매핑
        인성: "H", // 인성 → 신서귀
        사계: "H", // 사계 → 대정
        덕수: "H", // 덕수 → 대정
        남녕고: "B", // 남녕고 → 오일장
        대정고: "H", // 대정고 → 대정
        직통: "A", // 직통 → 제주
    };

    // 3개 파일의 데이터를 합치기
    const allBusData = [
        ...busDataPart1.buses,
        ...busDataPart2.buses,
        ...busDataPart3.buses,
    ];

    // JSON 데이터를 코드에서 사용하는 형식으로 변환
    // route의 정거장 이름을 ID로 변환
    let busSchedules = allBusData.map((bus) => ({
        id: bus.id,
        color: "orange", // 기본 색상 (나중에 로번별로 다른 색상 지정 가능)
        trips: bus.trips.map((trip, tripIdx) => {
            const mappedRoute = trip.route
                .filter((stationName) => stationName) // 빈 값 제거
                .map((stationName) => {
                    const id = stationNameToId[stationName];
                    if (!id) {
                        console.warn(
                            `⚠️ 매핑되지 않은 정거장: "${stationName}" (버스: ${bus.id}, ${tripIdx + 1}회차)`,
                        );
                        return null;
                    }
                    return id;
                })
                .filter((id) => id !== null); // null 제거

            // route와 times 길이 검증
            if (mappedRoute.length !== trip.times.length) {
                console.warn(
                    `⚠️ route와 times 길이 불일치: ${bus.id} ${tripIdx + 1}회차 (route: ${mappedRoute.length}, times: ${trip.times.length})`,
                );
                console.warn(`   route: ${mappedRoute.join(", ")}`);
                console.warn(`   times: ${trip.times.join(", ")}`);
            }

            return {
                route: mappedRoute,
                times: trip.times,
            };
        }),
    }));

    console.log(`✅ 총 ${busSchedules.length}개 로번 로드됨`);

    /* 
    // 기존 하드코딩된 데이터 (주석 처리)
    // 각 버스는 하루에 여러 회차(trips)를 운행할 수 있습니다.
    //
    // 데이터 구조:
    // {
    //     id: "버스 번호",           // 버스 식별자 (예: "202-1")
    //     color: "색상",             // 버스 표시 색상
    //     trips: [                  // 운행 회차 배열
    //         {
    //             route: ["A", "B", ...],  // 정거장 순서
    //             times: [830, 843, ...]   // 각 정거장 도착 시간 (HHMM 형식)
    //         }
    //     ]
    // }
    //
    // 운행 로직:
    // - 1회차 종료 후 다음 회차 시작 전까지 차고지에서 대기
    // - 같은 버스가 여러 회차를 순차적으로 운행
    // - 마지막 회차 종료 후 최종 정거장 차고지에 주차
    let busSchedules = [
        {
            id: "202-1", // 202번 버스 1호차
            color: "orange",
            trips: [
                {
                    // 1회차: A(제주) → M(등기소) → L(신서귀)
                    route: [
                        "A", // 제주 (출발)
                        "B", // 오일장
                        "C", // 하귀
                        "D", // 애월
                        "E", // 한림
                        "F", // 신창
                        "G", // 고산
                        "G", // 고산 (정차)
                        "H", // 대정
                        "I", // 화순
                        "J", // 창천
                        "K", // 중문
                        "L", // 신서귀
                        "M", // 등기소
                        "L", // 신서귀 (도착)
                    ],
                    times: [
                        830, 843, 903, 920, 942, 1004, 1014, 1019, 1039, 1054,
                        1103, 1114, 1131, 1141, 1151,
                    ],
                },
                {
                    route: [
                        "L",
                        "K",
                        "J",
                        "I",
                        "H",
                        "G",
                        "G",
                        "F",
                        "E",
                        "D",
                        "C",
                        "B",
                        "A",
                    ],
                    times: [
                        1258, 1313, 1324, 1333, 1351, 1409, 1414, 1424, 1446,
                        1508, 1526, 1544, 1611,
                    ],
                },
            ],
        },
        {
            id: "202-2",
            color: "orange",
            trips: [
                {
                    route: [
                        "L",
                        "K",
                        "J",
                        "I",
                        "H",
                        "G",
                        "G",
                        "F",
                        "E",
                        "D",
                        "C",
                        "B",
                        "A",
                    ],
                    times: [
                        708, 723, 734, 743, 801, 819, 824, 834, 856, 918, 936,
                        654, 1021,
                    ],
                },
                {
                    route: [
                        "A",
                        "B",
                        "C",
                        "D",
                        "E",
                        "F",
                        "G",
                        "G",
                        "H",
                        "I",
                        "J",
                        "K",
                        "L",
                        "M",
                        "L",
                    ],
                    times: [
                        1230, 1243, 1303, 1320, 1342, 1404, 1414, 1419, 1439,
                        1454, 1503, 1514, 1531, 1541,
                    ],
                },
            ],
        },
    ];
    */

    // ========================================
    // 5. 시뮬레이션 상태 관리
    // ========================================

    // 현재 시뮬레이션 시간 (자정 이후 분 단위, 0 ~ 1440)
    // - 0분 = 00:00 (자정)
    // - 720분 = 12:00 (정오)
    // - 1440분 = 24:00 (다음날 자정)
    // 초기값: 현재 시스템 시간
    let currentTime = $state(
        new Date().getHours() * 60 + new Date().getMinutes(),
    );

    // 애니메이션 재생 상태 (true: 재생 중, false: 정지)
    let isPlaying = $state(false);

    // 애니메이션 프레임 ID (requestAnimationFrame 반환값)
    let animationFrame;

    // 시간을 HH:MM 형식으로 포맷팅하는 derived 상태
    // 예: 510분 → "08:30", 1439분 → "23:59"
    let formattedTime = $derived.by(() => {
        const h = Math.floor(currentTime / 60); // 시간 계산
        const m = Math.floor(currentTime % 60); // 분 계산 (소수점 제거)
        // padStart(2, "0")로 한 자리 숫자 앞에 0 추가 (예: 8 → "08")
        return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    });

    // 현재 시스템 시간으로 시뮬레이션 시간 설정
    function goToCurrentTime() {
        const now = new Date();
        currentTime = now.getHours() * 60 + now.getMinutes();
    }

    // ========================================
    // 6. 차고지 정거장 관리
    // ========================================
    // 버스 노선에서 사용되는 시작/종료 정거장을 추적합니다.
    // 한번 차고지로 지정된 정거장은 계속 표시됩니다.
    //
    // 로직:
    // - 각 버스의 모든 trips를 순회
    // - 각 trip의 첫 정거장(시작)과 마지막 정거장(종료)을 Set에 추가
    // - Set을 배열로 변환하여 반환 (중복 제거됨)
    let usedGarageStations = $derived.by(() => {
        const garages = new Set();

        busSchedules.forEach((bus) => {
            bus.trips.forEach((trip) => {
                garages.add(trip.route[0]); // 시작 정거장
                garages.add(trip.route[trip.route.length - 1]); // 종료 정거장
            });
        });

        return Array.from(garages);
    });

    // ========================================
    // 7. 버스 위치 계산 (핵심 로직)
    // ========================================
    // 현재 시간(currentTime)을 기준으로 모든 버스의 위치를 계산합니다.
    //
    // 처리 순서:
    // 1. 각 버스의 모든 trips를 순회
    // 2. 각 trip의 시작/종료 시간과 현재 시간을 비교
    // 3. 상태에 따라 버스 위치 결정:
    //    - 운행 전: 시작 정거장 차고지에서 대기
    //    - 운행 중: 정거장 사이를 이동 (선형 보간)
    //    - 운행 후: 다음 trip 확인 또는 최종 차고지에 주차
    //
    // 차고지 배치 규칙:
    // - 상단 라인 정거장 (y ≤ 150): 정거장 위쪽에 차고지
    // - 하단 라인 정거장 (y > 150): 정거장 아래쪽에 차고지
    // - 같은 차고지에 여러 버스: 25px 간격으로 쌓임
    let activeBuses = $derived.by(() => {
        const buses = [];

        // 각 정거장별 차고지에 있는 버스 수를 카운트
        // Map<정거장ID, 버스수>
        // 예: garageCount.get("A") = 2 → A 정거장에 2대 대기 중
        const garageCount = new Map();

        busSchedules.forEach((bus) => {
            // busPlaced: 현재 버스가 이미 배치되었는지 추적
            // (한 버스는 한 번만 배치되어야 함)
            let busPlaced = false;

            // 각 버스의 모든 운행 회차를 순서대로 확인
            for (let tripIndex = 0; tripIndex < bus.trips.length; tripIndex++) {
                const trip = bus.trips[tripIndex];

                // route가 비어있거나 유효하지 않으면 스킵
                if (
                    !trip.route ||
                    trip.route.length === 0 ||
                    !trip.times ||
                    trip.times.length === 0
                ) {
                    console.warn(
                        `⚠️ 유효하지 않은 trip: ${bus.id} - ${tripIndex + 1}회차`,
                    );
                    continue;
                }

                // 시간 변환: HHMM → 분 단위
                // 예: [830, 843, ...] → [510, 523, ...]
                const convertedTimes = trip.times.map(timeToMinutes);
                const startTime = convertedTimes[0]; // 운행 시작 시간
                const endTime = convertedTimes[convertedTimes.length - 1]; // 운행 종료 시간

                // ==========================================
                // 상태 1: 운행 전 (Before Start)
                // ==========================================
                // 현재 시간이 이 trip의 시작 시간보다 이전인 경우
                // → 시작 정거장 차고지에서 대기
                if (currentTime < startTime) {
                    const startStationId = trip.route[0]; // 시작 정거장 ID
                    const startStation = stationMap.get(startStationId); // 정거장 정보

                    // 정거장을 찾을 수 없으면 스킵
                    if (!startStation) {
                        console.warn(
                            `⚠️ 정거장을 찾을 수 없음: "${startStationId}" (버스: ${bus.id}, ${tripIndex + 1}회차)`,
                        );
                        continue;
                    }

                    // 이 정거장에 이미 대기 중인 버스 수 확인
                    const count = garageCount.get(startStationId) || 0;
                    garageCount.set(startStationId, count + 1); // 카운트 증가

                    // 정거장 위치에 따라 차고지 위치 결정
                    // y ≤ 150: 상단 라인 → 정거장 위쪽에 차고지
                    // y > 150: 하단 라인 → 정거장 아래쪽에 차고지
                    const isTopRow = startStation.y <= 150;

                    buses.push({
                        id: `${bus.id} (${tripIndex + 1}회차)`, // 표시용 ID
                        x: startStation.x, // 정거장 x 좌표
                        y: isTopRow
                            ? startStation.y - 40 - count * 25 // 위쪽: 정거장 위에 배치
                            : startStation.y + 40 + count * 25, // 아래쪽: 정거장 아래에 배치
                        facing: 1, // 방향 (1: 오른쪽, -1: 왼쪽)
                        color: bus.color, // 버스 색상
                        status: "waiting", // 상태: 대기 중
                        stationId: startStationId, // 차고지 정거장 ID
                    });
                    busPlaced = true; // 버스 배치 완료
                    break; // 더 이상 다른 trip 확인 불필요
                }
                // ==========================================
                // 상태 2: 운행 중 (Active)
                // ==========================================
                // 현재 시간이 이 trip의 운행 시간 범위 내인 경우
                // → 정거장 사이를 이동 중 (선형 보간으로 위치 계산)
                else if (currentTime >= startTime && currentTime <= endTime) {
                    // 현재 시간이 어느 구간에 속하는지 찾기
                    // 구간: [정거장 i] → [정거장 i+1]
                    for (let i = 0; i < convertedTimes.length - 1; i++) {
                        const t1 = convertedTimes[i]; // i번째 정거장 도착 시간
                        const t2 = convertedTimes[i + 1]; // i+1번째 정거장 도착 시간

                        // 현재 시간이 이 구간에 속하는지 확인
                        if (currentTime >= t1 && currentTime <= t2) {
                            // 진행률 계산 (0.0 ~ 1.0)
                            // 예: t1=510, t2=523, currentTime=516
                            //     progress = (516-510)/(523-510) = 6/13 ≈ 0.46
                            const progress = (currentTime - t1) / (t2 - t1);

                            const stationId1 = trip.route[i]; // 출발 정거장 ID
                            const stationId2 = trip.route[i + 1]; // 도착 정거장 ID

                            const s1 = stationMap.get(stationId1); // 출발 정거장 정보
                            const s2 = stationMap.get(stationId2); // 도착 정거장 정보

                            // 정거장을 찾을 수 없으면 스킵
                            if (!s1 || !s2) {
                                console.warn(
                                    `⚠️ 정거장을 찾을 수 없음: "${stationId1}" 또는 "${stationId2}" (버스: ${bus.id})`,
                                );
                                continue;
                            }
                            // 버스 방향 계산
                            // 오른쪽으로 이동: facing = 1
                            // 왼쪽으로 이동: facing = -1
                            const facing = s2.x >= s1.x ? 1 : -1;

                            // 선형 보간(Linear Interpolation)으로 현재 위치 계산
                            // 공식: 현재값 = 시작값 + (끝값 - 시작값) * 진행률
                            // 예: s1.x=50, s2.x=150, progress=0.46
                            //     x = 50 + (150-50)*0.46 = 50 + 46 = 96
                            if (facing == 1) {
                            }
                            const x = s1.x + (s2.x - s1.x) * progress;
                            let y = s1.y + (s2.y - s1.y) * progress;
                            if (facing === 1) y += 11;
                            if (facing === -1) y -= 11;

                            buses.push({
                                id: `${bus.id} (${tripIndex + 1}회차)`,
                                x, // 보간된 x 좌표
                                y, // 보간된 y 좌표
                                facing, // 이동 방향
                                color: bus.color,
                                status: "active", // 상태: 운행 중
                            });
                            busPlaced = true;
                            break; // 구간을 찾았으므로 루프 종료
                        }
                    }
                    if (busPlaced) break; // 버스 배치 완료, trip 루프 종료
                }
                // ==========================================
                // 상태 3: 운행 종료 후 (After End)
                // ==========================================
                // 현재 시간이 이 trip의 종료 시간보다 이후인 경우
                else if (currentTime > endTime) {
                    // 다음 trip이 있는지 확인
                    if (tripIndex < bus.trips.length - 1) {
                        // 다음 trip이 있으면 continue로 다음 trip 확인
                        // (다음 trip의 시작 시간 전이면 그 차고지에서 대기)
                        continue;
                    }
                    // 마지막 trip인 경우 → 최종 차고지에 주차
                    else {
                        const endStationId = trip.route[trip.route.length - 1]; // 종료 정거장 ID
                        const endStation = stationMap.get(endStationId); // 정거장 정보

                        // 정거장을 찾을 수 없으면 스킵
                        if (!endStation) {
                            console.warn(
                                `⚠️ 종료 정거장을 찾을 수 없음: "${endStationId}" (버스: ${bus.id})`,
                            );
                            break;
                        }

                        // 이 정거장에 이미 주차된 버스 수 확인
                        const count = garageCount.get(endStationId) || 0;
                        garageCount.set(endStationId, count + 1);

                        // 정거장 위치에 따라 차고지 위치 결정
                        const isTopRow = endStation.y <= 150;

                        buses.push({
                            id: bus.id, // 회차 표시 없음 (최종 주차)
                            x: endStation.x,
                            y: isTopRow
                                ? endStation.y - 40 - count * 25 // 위쪽 차고지
                                : endStation.y + 40 + count * 25, // 아래쪽 차고지
                            facing: -1, // 왼쪽 방향 (복귀)
                            color: bus.color,
                            status: "finished", // 상태: 운행 종료
                            stationId: endStationId, // 차고지 정거장 ID
                        });
                        busPlaced = true;
                        break;
                    }
                }
            }
        });
        return buses; // 계산된 모든 버스 위치 반환
    });

    // ========================================
    // 8. 애니메이션 컨트롤
    // ========================================

    // 재생/정지 토글 함수
    // Play 버튼 클릭 시 호출됩니다.
    function togglePlay() {
        if (isPlaying) {
            // 현재 재생 중이면 정지
            isPlaying = false;
            cancelAnimationFrame(animationFrame); // 애니메이션 프레임 취소
        } else {
            // 현재 정지 중이면 재생
            isPlaying = true;
            play(); // 애니메이션 시작
        }
    }

    // 애니메이션 재생 함수
    // requestAnimationFrame을 사용한 부드러운 애니메이션
    function play() {
        if (!isPlaying) return; // 정지 상태면 종료

        currentTime += 0.1; // 시간 0.1분 증가 (0.1배속)

        // 24시간(1440분)을 넘으면 0으로 리셋 (루프)
        if (currentTime > 1440) currentTime = 0;

        // 다음 프레임 요청 (재귀 호출)
        animationFrame = requestAnimationFrame(play);
    }

    // ========================================
    // 9. SVG ViewBox 관리 (Pan & Zoom)
    // ========================================
    // SVG 뷰포트 설정
    // x, y: 좌상단 시작 좌표
    // width, height: 보이는 영역의 크기
    let viewBox = $state({ x: 0, y: 0, width: 1100, height: 400 });
    let svgElement; // SVG 요소 참조 (bind:this로 연결)

    // ========================================
    // 10. 툴팁 및 인터랙션
    // ========================================
    // 툴팁 상태 관리
    let tooltip = $state({
        visible: false, // 툴팁 표시 여부
        x: 0, // SVG 좌표계 x (SVG 툴팁용)
        y: 0, // SVG 좌표계 y (SVG 툴팁용)
        clientX: 0, // 화면 좌표 x (HTML 툴팁용)
        clientY: 0, // 화면 좌표 y (HTML 툴팁용)
        text: "", // 툴팁 텍스트
        busId: "", // 버스 ID
    });

    // 버스 클릭 이벤트 핸들러
    function handleBusClick(busId) {
        alert(`버스 클릭됨: ${busId}`);
    }

    // 버스에 마우스 올렸을 때 (툴팁 표시)
    function handleBusMouseEnter(event, bus) {
        // ==========================================
        // 툴팁 좌표 계산
        // ==========================================
        // 두 가지 좌표계를 사용합니다:
        // 1. 화면 좌표 (clientX, clientY): HTML 툴팁용
        // 2. SVG 좌표 (svgX, svgY): SVG 툴팁용 (ViewBox 고려)

        // 1. 마우스 이벤트에서 화면 좌표 가져오기
        const { clientX, clientY } = event;

        // 2. SVG 요소의 화면상 위치와 크기 정보 가져오기
        const rect = svgElement.getBoundingClientRect();

        // 3. 화면 좌표를 SVG ViewBox 좌표로 변환
        // 공식: viewBoxCoord = viewBoxStart + (clientCoord - rectStart) * (viewBoxSize / rectSize)
        //
        // 예시:
        // - viewBox = {x: 0, y: 0, width: 800, height: 400}
        // - rect = {left: 100, top: 50, width: 1600, height: 800}
        // - clientX = 500
        // → svgX = 0 + (500 - 100) * (800 / 1600) = 400 * 0.5 = 200
        const svgX =
            viewBox.x + (clientX - rect.left) * (viewBox.width / rect.width);
        const svgY =
            viewBox.y + (clientY - rect.top) * (viewBox.height / rect.height);

        // 툴팁 상태 업데이트
        tooltip = {
            visible: true,
            x: svgX, // SVG 좌표 (SVG 툴팁용)
            y: svgY,
            clientX: clientX, // 화면 좌표 (HTML 툴팁용)
            clientY: clientY,
            text: `${bus.id} (${bus.status})`, // 툴팁 텍스트
            busId: bus.id,
        };
    }

    // 버스에서 마우스 벗어났을 때 (툴팁 숨김)
    function handleBusMouseLeave() {
        tooltip.visible = false;
    }
</script>

<div class="container">
    <div class="controls">
        <button onclick={togglePlay}>{isPlaying ? "Stop" : "Play"}</button>
        <button onclick={goToCurrentTime}>Current Time</button>
        <div class="time-control">
            <span class="time-display">{formattedTime}</span>
            <input
                type="range"
                min="240"
                max="1440"
                step="1"
                bind:value={currentTime}
                style="width: 400px;"
            />
        </div>
    </div>

    <!-- HTML 툴팁 (fixed/absolute positioning) -->
    {#if tooltip.visible}
        <div
            class="html-tooltip"
            style="top: {tooltip.clientY + 20}px; left: {tooltip.clientX +
                20}px;"
        >
            [HTML Tooltip] {tooltip.text}
        </div>
    {/if}

    <svg
        bind:this={svgElement}
        width="100%"
        height="600"
        viewBox="{viewBox.x} {viewBox.y} {viewBox.width} {viewBox.height}"
        style="border: 1px solid #ccc; background: #f9f9f9;"
    >
        <!-- 1. 연결 선 (Tracks) 그리기 -->
        {#each tracks as [startId, endId]}
            {@const s1 = stationMap.get(startId)}
            {@const s2 = stationMap.get(endId)}
            <line
                x1={s1.x}
                y1={s1.y}
                x2={s2.x}
                y2={s2.y}
                stroke="#ddd"
                stroke-width="4"
                stroke-linecap="round"
            />
        {/each}

        <!-- 2. 정거장 (Nodes) 그리기 -->
        {#each stations as station}
            <g transform="translate({station.x}, {station.y})">
                <circle r="15" fill="white" stroke="#333" stroke-width="2" />
                <text
                    y="5"
                    text-anchor="middle"
                    font-size="12"
                    font-weight="bold"
                    fill="#333">{station.label}</text
                >
            </g>
        {/each}

        <!-- 3. 차고지 영역 그리기 (한번 생성되면 계속 유지) -->
        {#each usedGarageStations as stationId}
            {@const station = stationMap.get(stationId)}
            {@const isTopRow = station.y <= 150}

            <!-- 간단한 차고지 표시 -->
            <text
                x={station.x}
                y={isTopRow ? station.y - 25 : station.y + 35}
                text-anchor="middle"
                font-size="16"
            >
                🅿️
            </text>
        {/each}

        <!-- 4. 버스 그리기 -->
        {#each activeBuses as bus}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <g
                transform="translate({bus.x}, {bus.y})"
                onmouseenter={(e) => handleBusMouseEnter(e, bus)}
                onmouseleave={handleBusMouseLeave}
                onclick={() => handleBusClick(bus.id)}
                role="button"
                tabindex="0"
                class="bus-group"
            >
                <g transform="scale({bus.facing}, 1)">
                    <rect
                        x="-15"
                        y="-10"
                        width="30"
                        height="20"
                        rx="5"
                        fill={bus.color}
                        stroke="black"
                    />
                    <!-- 창문 -->
                    <rect x="5" y="-5" width="5" height="10" fill="white" />
                </g>
                <text y="-15" text-anchor="middle" font-size="10" fill="black"
                    >{bus.id}</text
                >
            </g>
        {/each}

        <!-- 4. SVG 툴팁 (SVG 내부 요소로 렌더링) -->
        {#if tooltip.visible}
            <g
                transform="translate({tooltip.x}, {tooltip.y - 40})"
                style="pointer-events: none;"
            >
                <rect
                    x="-60"
                    y="-15"
                    width="120"
                    height="30"
                    rx="5"
                    fill="rgba(0,0,0,0.8)"
                />
                <text
                    x="0"
                    y="5"
                    text-anchor="middle"
                    fill="white"
                    font-size="12"
                >
                    [SVG] {tooltip.text}
                </text>
                <!-- 말풍선 꼬리 -->
                <path d="M -5 15 L 0 20 L 5 15" fill="rgba(0,0,0,0.8)" />
            </g>
        {/if}
    </svg>
    <div class="legend">202</div>
</div>

<style>
    .container {
        padding: 20px;
        font-family: sans-serif;
    }
    .controls {
        margin-bottom: 10px;
        display: flex;
        gap: 10px;
        align-items: center;
    }
    .legend {
        margin-top: 10px;
        color: #555;
    }
    .bus-group {
        cursor: pointer;
    }
    .time-control {
        display: flex;
        align-items: center;
        gap: 10px;
        background: #fff;
        padding: 5px 10px;
        border: 1px solid #ddd;
        border-radius: 4px;
    }
    .html-tooltip {
        position: fixed; /* 브라우저 뷰포트 기준 */
        background: white;
        border: 1px solid #333;
        padding: 5px 10px;
        border-radius: 4px;
        box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
        z-index: 1000;
        pointer-events: none;
        font-size: 12px;
        font-weight: bold;
    }
    .time-display {
        font-family: monospace;
        font-weight: 900; /* 더 굵게 */
        font-size: 2em; /* 더 크게 */
        color: #333;
        margin-right: 10px;
    }
</style>
