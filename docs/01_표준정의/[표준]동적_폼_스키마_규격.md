---
제목: 동적 폼 스키마 및 데이터 바인딩 규격 (v1.0)
날짜: 2026-03-12
작성자: Gemini CLI Agent
카테고리: 01_표준정의
태그: #DynamicForm #JSON-Schema #UI-Generator #Metadata
상태: Completed
---

# 📋 동적 폼 스키마 규격 (Dynamic Form Standard)

> 이 문서는 JSON 데이터를 기반으로 UI 폼을 자동 생성하기 위한 필드 타입과 데이터 구조 표준을 정의합니다.

---

## 1. 개요 (Overview)
본 시스템은 설정(Configuration) 화면의 하드코딩을 배제하고, **App Registry**의 `config_schema` 메타데이터를 기반으로 UI를 동적 생성합니다. 이를 통해 새로운 앱 엔진이나 서비스 추가 시 별도의 프론트엔드 작업 없이 관리 도구를 즉시 확보합니다.

---

## 2. 스키마 구조 (Schema Structure)

전체 스키마는 **필드 객체의 배열**로 구성됩니다.

```json
[
  {
    "key": "unique_field_key",
    "label": "화면 표시 이름",
    "type": "field_type",
    "default": "기본값",
    "placeholder": "힌트 메시지",
    "options": [] // (Select 타입 전용)
  }
]
```

---

## 3. 지원 필드 타입 (Supported Field Types)

| 타입명 (`type`) | UI 요소 | 설명 |
| :--- | :--- | :--- |
| **`text`** | `<input type="text">` | 일반 문자열 입력 |
| **`number`** | `<input type="number">` | 숫자 입력 (정수/실수) |
| **`boolean`** | `Switch / Checkbox` | On/Off 상태 제어 |
| **`select`** | `<select>` | 미리 정의된 `options` 중 하나 선택 |
| **`textarea`**| `<textarea>` | 긴 문장이나 설명 입력 |
| **`color`** | `<input type="color">` | 시스템 포인트 색상 선택 |

---

## 4. 데이터 바인딩 원칙 (Binding Principle)

1.  **양방향 연동**: 엔진은 `Schema`와 `Value` 객체를 동시에 입력받습니다.
2.  **독립성**: 폼 엔진은 데이터의 저장(Save) 로직을 직접 수행하지 않고, 최종 결과물인 `JSON Object`를 부모 컴포넌트에게 전달(Dispatch)만 합니다.
3.  **유효성 검사**: 각 필드 타입에 맞는 기본적인 데이터 형식 검증을 렌더링 시점에 수행합니다.

---

## 5. 기대 효과 (Impact)

- **개발 속도**: 설정 화면 코딩 시간 90% 단축.
- **일관성**: 모든 앱 엔진의 설정 UI가 동일한 룩앤필(Look & Feel)을 유지.
- **유연성**: DB 값 수정만으로 UI 구성을 실시간 변경 가능.

---

### 📜 변경 이력
- **2026-03-12**: [Gemini CLI] 동적 폼 엔진 구축을 위한 기초 규격 초안 작성.
