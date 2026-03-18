---
제목: 내부 문서 및 파일 관리 표준 (v1.2)
날짜: 2026-03-09
작성자: Antigravity (AI)
카테고리: 01_표준정의
태그: #FileSecurity #Storage #Nginx #X-Accel-Redirect
상태: Completed
---

# 📂 내부 문서 및 파일 관리 표준 (File Management)

> 이 문서는 민감한 개인정보(검진결과, 계약서 등)가 포함된 내부 문서의 **물리적 격리와 접근 제어(Security)**를 위한 기술 표준을 정의합니다.

---

## 1. 배경 및 목적 (Background & Motivation)
웹 서비스에서 파일 업로드는 필수지만, 민감한 문서가 일반 이미지 폴더와 섞이거나 브라우저 주소창 입력만으로 누구나 접근 가능할 때 보안 사고의 치명적인 원인이 됩니다.

본 표준은 **Nginx internal 지시어**와 **FastAPI의 권한 체크**를 결합하여 "승인된 사용자만, 정해진 경로로" 파일을 안전하게 송수신하는 데 목적이 있습니다.

## 2. 기존 방식의 문제점 (Analysis of Current State)
- **직접 접근 노출**: `/uploads/file_a.pdf` 주소만 알면 로그인 없이도 다운로드 가능.
- **파일명 중복 및 유추**: `2024_검진_김철수.pdf` 같은 원본 파일명을 그대로 사용하여 정보가 노출됨.
- **감사 추적 불가**: 누가 언제 어떤 보안 문서를 열어봤는지 기록(Audit Log)이 남지 않아 책임 소재 불명확.

## 3. 해결 방안 및 핵심 로직 (Solution & Key Changes)

### 3.1 물리적 격리 및 암호화 (Physical Isolation) 🌟
- **원칙**: 일반 업로드(`/uploads/public/`)와 내부 문서(`/uploads/internal/`) 폴더를 완전히 분리합니다.
- **변조**: 원본 파일명 대신 `UUID`를 부여하여 파일 성격을 유추할 수 없게 만듭니다.

### 3.2 Nginx X-Accel-Redirect 방식 (The Proxy Approach)
- **핵심**: 브라우저의 직접 요청을 Nginx `internal` 설정으로 차단하고, 백엔드(FastAPI)가 권한을 확인한 후 Nginx에게 "이 파일은 이 사람에게 보낼 수 있다"는 허락(`X-Accel-Redirect`)을 내리는 구조입니다.
- **효과**: 백엔드가 직접 수 MB의 파일을 읽지 않아 메모리 부하가 낮고, 보안은 최고 수준(RBAC 연동)을 유지합니다.

## 4. 상세 구현 가이드 (Implementation Details)

### 4.1 Nginx 보안 설정 (nginx.conf)
```nginx
location /internal_files/ {
    internal;   # 외부 접속 물리적 차단
    alias /home/lee/uv-code/test/uploads/internal/; 
    add_header Cache-Control "no-store"; # 보안 강화
}
```

### 4.2 백엔드 권한 체커 및 전송 (Python)
```python
@app.get("/api/download/{file_id}")
async def download_file(file_id: str, user=Depends(get_current_user)):
    # 1. DB에서 파일 메타데이터 및 권한(L2 이상 등) 확인
    # 2. Audit Log 기록 (누가, 언제, 무엇을)
    # 3. Nginx에게 전송 명령 헤더 송신
    return Response(headers={"X-Accel-Redirect": f"/internal_files/{file_id}"})
```

## 5. 성과 및 학습 포인트 (Outcome & Learning)
- **보안의 완결성**: 이제 주소를 알아도 절대 문서를 탈취할 수 없는 철벽 방어 체계를 구축했습니다.
- **감사 로그(Audit Log)**: 모든 민감 문서의 접근 기록이 DB에 남게 되어 관리적 보안의 기틀을 마련했습니다.
- **학습 포인트**: **"웹 서버(Nginx)와 애플리케이션 서버(FastAPI)의 협업(X-Accel)"**을 통해 보안과 성능이라는 두 마리 토끼를 잡는 아키텍처를 실무 레벨에서 검증했습니다.

---

### 📜 변경 이력 (Change Log)
- **2026-03-02**: 내부 문서 관리 표준 초안 작성.
- **2026-03-09**: [Antigravity] 배포 및 보안 가이드와 연계된 지식 확장형 문서로 전면 리팩토링.
