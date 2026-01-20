# 설정 관리 요구사항

## 1. 현재 상태

### 1.1 구조
- CSV 파일 (`/root/this/conf/`) → SQLite DB (`/root/this/db/edge.db`)
- 테이블: `intf`, `blck`, `blck_map`, `tag`

### 1.2 현재 테이블 구조

```
intf (인터페이스)
├── intf: 인터페이스 ID (PK)
├── prot: 프로토콜 (mtc, ouc, mqc 등)
├── host, port: 연결 정보
├── prop1~5: 프로토콜별 속성
├── secu1~5: 보안 설정
└── tout, rtr: 타임아웃, 재시도

blck (블록)
├── blck: 블록 ID (PK)
├── intf: 인터페이스 FK
├── rw: 방향 (ro, wo, rw)
├── trig: 트리거 (cyc, onc, sub)
├── tm: 주기
├── stby: 대기 시간
└── prop1~5: 프로토콜별 속성

blck_map (태그 매핑)
├── blck: 블록 FK
├── tag: 태그 ID
├── idx: 인덱스
└── prop1~5: 프로토콜별 속성

tag (태그 정의)
├── tag: 태그 ID (PK)
├── cmt: 설명
└── init: 초기값
```

### 1.3 문제점
- `prop1~5` 필드가 프로토콜마다 의미가 다름 (가독성 저하)
  - Modbus: prop1=unit_id, prop2=function_code, prop3=address, prop4=datatype
  - OPC UA: prop1=node_id
  - MQTT: prop1=topic
- 설정 수동 편집 불편
- csv, SQL식 행렬 데이터만 입력 가능해 설정 유연성/확장성 떨어짐
- Git diff로 변경 추적 어려움 (SQLite 바이너리)

---

## 2. 지원 프로토콜

| 프로토콜 | 코드 |
|---------|------|
| Nodi Edge Internal | nei |
| Data Store Client | dsc |
| Modbus TCP Client | mtc |
| Modbus TCP Server | mts |
| Modbus RTU via TCP Client | mvc |
| Modbus RTU via TCP Server | mvs |
| Modbus RTU Client | mrc |
| Modbus RTU Server | mrs |
| OPC UA Client | ouc |
| OPC UA Server | ous |
| MQTT Client (Pub/Sub) | mqc |
| MQTT Broker | mqs |
| Kafka Client (Prod/Cons) | kfc |
| Kafka Server | kfs |
| Relation DB Client | rdc |
| REST API Client | rac |
| REST API Server | ras |

---

## 3. 기능 요구사항

### 3.1 로컬 영속성
- 설정은 패키지와 분리된 경로에 저장 (`/home/nodi/nodi-edge-data/`)
- 패키지 배포/업데이트 시에도 설정 보존
- 로컬 기기에서 독립적으로 동작

### 3.2 설정 유연성
- 프로토콜별 설정 필드 개수, 구조를 유연하게 변경 가능해야 함
    - 예: mtc는 `unit_id`, `node_id`, `topic`, `function_code` 등
    - 예: ouc는 `node_id`, `browse_path`, `read-only/writeable` 등
- 공통 설정도 입력할 수 있어야 함
    - 예: scale-a, scale-b (y = ax + b 연산 지원)

### 3.3 설정 입력
- 폼 기반 입력 → DB 저장 (현재는 csv 입력 → DB 저장. 개선 희망.)
- 반복된 형태의 데이터를 쉽게 복사 → 붙여넣기 가능해야 함
- 복사 → 붙여넣기 시 숫자를 자동 갱신 등 기능 필요 (엑셀과 유사하게)

### 3.4 웹 UI 입력
- Django 기반 웹 시스템으로 사용자가 쉽게 설정 입력

### 3.5 포맷 설명 용이
- 사용자에게 "이렇게 작성하세요" 문서화가 쉬워야 함
- 템플릿/샘플 제공
- 스키마 명확히 정의

### 3.6 클라우드 동기화
- 로컬 설정을 원격 클라우드에 저장/복원
- 다중 기기 설정 관리
- 향후 구현 예정

### 3.7 명시적 필드명
- `prop1~5` → 프로토콜별 명확한 필드명을 쓰면 더 좋음 (선택적)
    - 예: `unit_id`, `node_id`, `topic`, `function_code` 등

---

## 4. 데이터 구조

### 4.1 계층 구조

```
인터페이스 (Interface)
│
├── 연결 정보
│   ├── host, port
│   ├── 인증 정보 (username, password, 인증서 등)
│   └── 타임아웃, 재시도
│
└── 블록 (Block) [1:N]
    │
    ├── 통신 설정
    │   ├── 방향 (read, write, subscribe, publish)
    │   ├── 트리거 (cyclic, on_change, subscription)
    │   └── 주기
    │
    └── 태그 매핑 (Tag) [1:M]
        ├── 태그 ID (databus 태그)
        └── 프로토콜별 주소 정보
```

### 4.2 프로토콜별 필드

#### Modbus TCP/RTU
```
Interface:
  - host, port (TCP) / device, baudrate (RTU)

Block:
  - unit_id: 슬레이브 ID
  - function_code: 펑션 코드 (1, 2, 3, 4, 5, 6, 15, 16)
  - start_address: 시작 주소

Tag:
  - offset: 블록 내 오프셋
  - datatype: 데이터 타입 (int16, uint16, int32, float32 등)
  - scale: 스케일 팩터
  - mask: 비트 마스크 (옵션)
```

#### OPC UA
```
Interface:
  - endpoint: OPC UA 서버 엔드포인트
  - security_mode: 보안 모드
  - certificate, private_key: 인증서

Block:
  - namespace_uri: 네임스페이스 URI

Tag:
  - node_id: 노드 ID
  - sampling_interval: 샘플링 주기 (subscription)
```

#### MQTT
```
Interface:
  - host, port: 브로커 주소
  - client_id: 클라이언트 ID
  - username, password: 인증

Block:
  - qos: QoS 레벨

Tag:
  - topic: 토픽
  - payload_type: JSON, raw, etc.
```

#### SQL
```
Interface:
  - driver: postgresql, mysql, mssql, etc.
  - host, port, database
  - username, password

Block:
  - query: SQL 쿼리
  - parameters: 쿼리 파라미터

Tag:
  - column: 컬럼명
  - datatype: 데이터 타입
```

---

## 5. 사용 시나리오

### 5.1 초기 설정 (파일 기반)
1. 템플릿/샘플 파일 제공
2. 사용자가 파일 편집
3. 시스템에 로드 (import)

### 5.2 웹 UI 입력 (향후)
1. Django 웹 UI 접속
2. 폼으로 인터페이스/블록/태그 입력
3. DB에 저장
4. 앱 재시작 또는 설정 리로드

### 5.3 백업/복원
1. 현재 설정을 파일로 내보내기 (export)
2. 클라우드에 업로드 (동기화)
3. 다른 기기에서 다운로드
4. 시스템에 로드 (import)

### 5.4 앱 실행
1. 앱 시작 시 설정 로드
2. 인터페이스별 연결 수립
3. 블록별 통신 스케줄 실행
4. 태그 데이터 databus에 발행/구독

---

## 6. 저장 경로

```
/home/nodi/nodi-edge-data/
├── backup/              # 클라우드 동기화 대상
├── config/
│   ├── apps/            # 앱별 설정
│   └── interfaces/      # 인터페이스 설정 파일
├── data/
│   └── snapshots/       # databus 스냅샷
└── log/                 # 로그 파일
```

---

## 7. 미결정 사항

### 7.1 입력 포맷
- [ ] YAML
- [ ] JSON
- [ ] Django 모델 직접

### 7.2 저장 포맷
- [ ] SQLite
- [ ] JSON 파일
- [ ] 둘 다 (DB + 백업용 JSON)

### 7.3 Django 연동 시점
- [ ] 초기부터 Django 모델 기반 설계
- [ ] 나중에 Django 붙이기 (현재는 파일 기반)

---

## 8. 개선 방향 (권장)

### 8.1 Django 모델 + JSON 내보내기

```
[웹 UI] → [Django 모델/SQLite] ←→ [JSON 파일 백업]
              ↓
        [앱이 직접 읽기]
```

### 8.2 장점
- **웹 입력**: Django ORM과 자연스럽게 연동
- **포맷 설명**: JSON Schema로 명확한 스키마 정의
- **Git 추적**: JSON export로 텍스트 기반 버전 관리
- **관계형 데이터**: FK로 명확한 관계 표현

### 8.3 워크플로우
1. **신규 설치**: JSON 템플릿 제공 → 사용자 편집 → `loaddata`
2. **웹 UI**: Django 폼 입력 → DB 저장 → JSON `dumpdata` (백업)
3. **앱 실행**: Django ORM으로 설정 로드
4. **클라우드 동기화**: JSON 파일 업로드/다운로드
