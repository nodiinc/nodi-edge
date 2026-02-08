# 설정 관리 요구사항

---

## 1. 현재 상태

### 1.1 구조

CSV 파일을 파싱하여 SQLite DB에 적재하는 방식.

```
[CSV 파일] → csv_to_db 로더 → [SQLite DB] → 앱이 읽기
 conf/                          db/edge.db
```

### 1.2 CSV 파일 목록

| 파일 | 역할 | DB 테이블 |
|------|------|-----------|
| `intf.csv` | 인터페이스 (연결 정보) | `intf` |
| `blck.csv` | 블록 (논리 단위) | `blck` |
| `blck_map.csv` | 태그 매핑 (블록 ↔ 태그) | `blck_map` |
| `tag.csv` | 태그 정의 | `tag` |
| `arcv.csv` | 아카이브 설정 | `arcv` |
| `arcv_map.csv` | 아카이브 ↔ 태그 매핑 | `arcv_map` |

### 1.3 현재 테이블 구조

```
intf (인터페이스)
├── intf: 인터페이스 ID (PK)
├── cmt: 설명
├── prot: 프로토콜 코드 (mtc, ouc, mqc 등)
├── host, port: 연결 정보
├── prop1~5: 프로토콜별 속성 (의미가 프로토콜마다 다름)
├── secu1~5: 보안 설정 (의미가 프로토콜마다 다름)
├── tout: 타임아웃 (초)
└── rtr: 재시도 간격 (초)

blck (블록)
├── blck: 블록 ID (PK)
├── cmt: 설명
├── use: 사용 여부 (Y/N)
├── intf: 인터페이스 FK → intf.intf
├── prop1~5: 프로토콜별 속성
├── rw: 방향 (ro, wo, wr)
├── trig: 트리거 (cyc, onc, sub)
├── tm: 주기 (초)
└── stby: 대기 시간 (초)

blck_map (태그 매핑)
├── blck: 블록 FK → blck.blck
├── tag: 태그 FK → tag.tag
├── idx: 인덱스 타입 (v, q, t 등)
└── prop1~5: 프로토콜별 속성

tag (태그 정의)
├── tag: 태그 ID (PK)
├── cmt: 설명
└── init: 초기값
```

### 1.4 현재 CSV 예시

**intf.csv** — 인터페이스 정의:
```csv
intf,cmt,prot,host,port,prop1,prop2,prop3,prop4,prop5,secu1,secu2,secu3,secu4,secu5,tout,rtr
ouc,,ouc,localhost,4841,nodi/,,,,,anonymous,/root/edge/sys/nodi_cert.der,/root/edge/sys/nodi_pkey.pem,,,5.0,10.0
mtc,,mtc,0.0.0.0,502,,,,,,,,,,,5.0,10.0
```

**blck.csv** — 블록 정의:
```csv
blck,cmt,use,intf,prop1,prop2,prop3,prop4,prop5,rw,trig,tm,stby
mtc-w,,Y,mtc,0,,,,,wo,cyc,1,1.0
ouc-a,,Y,ouc,urn:freeopcua:python:server,,,,,ro,onc,1,15.0
```

**blck_map.csv** — 태그 매핑 (실제 수백~수천 행):
```csv
blck,tag,idx,prop1,prop2,prop3,prop4,prop5
dsc-fems,elec-010-00_m_Va,v,,,,,
dsc-fems,elec-010-00_m_Vb,v,,,,,
dsc-fems,elec-010-00_m_Vc,v,,,,,
... (동일 패턴 수백 줄 반복)
```

### 1.5 prop1~5의 프로토콜별 실제 의미

`prot` 테이블에 정의된 각 propN의 의미:

| 레이어 | mtc (Modbus TCP Client) | ouc (OPC UA Client) | ous (OPC UA Server) |
|--------|-------------------------|---------------------|---------------------|
| intf.prop1 | - | Path (URL) | Path (URL) |
| intf.prop2 | - | - | Server Name (URI) |
| blck.prop1 | 0 or 1-based addressing | Server URI (namespace) | Server URI (namespace) |
| map.prop1 | Unit ID | Node ID | Identifier |
| map.prop2 | Function Code | - | Path |
| map.prop3 | Address | - | Writable |
| map.prop4 | Data Type | - | - |
| map.prop5 | Bit or Multiple Mask | - | - |

> CSV 파일에서는 `prop1,prop2,prop3`으로만 보이므로, `prot` 테이블을 별도 참조하지 않으면
> 각 필드의 의미를 알 수 없다.

---

## 2. 현재 방식의 장점과 한계

### 2.0 CSV 입력의 전략적 위치

현재 CSV 기반 입력은 다음 두 가지 목적을 위한 **과도기적 수단**이다:

1. **대량 설정 입력**: 웹 UI 없이도 수백~수천 개 태그를 빠르게 입력
2. **웹 UI 구현 전 브릿지**: 웹 UI가 완성되기 전까지 사용자가 설정을 관리하는 유일한 방법

**최종 목표는 웹 UI를 통한 설정 입력**이며, 파일 기반 입력(CSV/YAML)은 웹 UI 완성 후에도
대량 임포트/익스포트 용도로 계속 지원한다.

> **업계 레퍼런스: KEPServerEX**
>
> 산업 자동화 분야에서 가장 널리 사용되는 KEPServerEX는 다음과 같은 설정 관리 방식을 제공한다:
>
> - **기본 입력**: GUI 기반 설정 (채널 → 디바이스 → 태그 계층)
> - **대량 입력**: CSV 파일로 태그를 익스포트/임포트
> - **자동화**: API를 통한 프로그래밍 방식 설정
>
> KEPServerEX의 CSV 익스포트/임포트는 **GUI에서 설정한 내용을 파일로 내보내고,
> 사용자가 엑셀 등으로 대량 편집한 뒤 다시 임포트**하는 워크플로우이다.
> 이 패턴은 nodi-edge에서도 동일하게 적용할 수 있다.

### 2.1 장점 (유지할 부분)

- **단순함**: CSV는 누구나 이해할 수 있는 포맷
- **엑셀 호환**: 복사/붙여넣기, 대량 편집 용이
- **검증된 구조**: interface → block → block_map 계층이 실무에서 잘 동작함
- **분리된 관심사**: 연결 정보(intf), 동작 설정(blck), 태그 매핑(blck_map)이 명확히 분리됨

### 2.2 한계 (개선할 부분)

#### P1. 범용 컬럼명 (`prop1~5`)의 의미 불투명

- `prop1`이 Modbus에서는 Unit ID, OPC UA에서는 Node ID
- **설정 파일만 보고 의미를 알 수 없음** → 별도 `prot` 테이블 참조 필요
- 비개발자에게 특히 혼란스러움

#### P2. 고정 5개 슬롯의 확장성 부족

- 프로토콜에 속성이 6개 이상 필요하면 구조를 변경해야 함
- 속성이 2개뿐인 프로토콜은 빈 컬럼(`,,,,`)이 반복됨
- 새로운 공통 속성(예: scale_a, scale_b) 추가 시 전체 스키마 변경 필요

#### P3. blck_map.csv의 폭발적 반복

- 실제 운영에서 한 블록에 수백~수천 개의 태그가 매핑됨
- 동일 패턴(예: `elec-010-{00~04}_m_{Va,Vb,...Qc}`)이 한 줄씩 반복
- 현재 blck_map.csv: ~300행 → 실제 운영에서는 수천 행 예상
- 수작업 편집 시 오류 발생 확률 높음

#### P4. 자기 설명(self-documenting) 불가

- CSV에는 주석 메커니즘이 없음
- 각 필드의 의미, 유효 값 범위, 단위, 예시를 설정 파일 자체에 기술 불가
- 별도 문서를 항상 옆에 두고 참조해야 함

#### P5. Git diff 비친화적

- 최종 저장 형태가 SQLite 바이너리
- 변경 이력 추적이 어려움

---

## 3. 지원 프로토콜

| 프로토콜 | 코드 | 비고 |
|---------|------|------|
| Nodi Edge Internal | nei | 내부 통신 |
| Data Store Client | dsc | 내부 데이터 저장소 |
| Modbus TCP Client | mtc | |
| Modbus TCP Server | mts | |
| Modbus RTU via TCP Client | mvc | |
| Modbus RTU via TCP Server | mvs | |
| Modbus RTU Client | mrc | |
| Modbus RTU Server | mrs | |
| OPC UA Client | ouc | |
| OPC UA Server | ous | |
| MQTT Client (Pub/Sub) | mqc | |
| MQTT Broker | mqs | |
| Kafka Client (Prod/Cons) | kfc | |
| Kafka Server | kfs | |
| Relation DB Client | rdc | PostgreSQL, SQLite 등 |
| REST API Client | rac | |
| REST API Server | ras | |

---

## 4. 설계 원칙

### 4.1 대상 사용자 및 최종 목표

- **비개발자(일반 사용자)** 가 직접 설정 파일을 편집할 수 있어야 함
- 프로그래밍 지식 없이도 구조를 이해하고 작성 가능해야 함
- "이렇게 작성하세요" 라고 설명하기 쉬워야 함

**최종 목표 (웹 UI 중심 운영):**

```
[웹 UI] ←── 사용자의 기본 입력 수단 (최종 목표)
   │
   ├── 인터페이스/블록/태그를 폼으로 입력/수정/삭제
   ├── 대량 태그: CSV 파일 임포트 (엑셀에서 작성 → 업로드)
   ├── 설정 익스포트: CSV/YAML 파일로 내보내기
   └── 설정 임포트: CSV/YAML 파일 업로드로 대량 입력
```

**파일 기반 입력의 위치:**

| 단계 | 입력 수단 | 파일 입력의 역할 |
|------|----------|-----------------|
| 현재 (웹 UI 전) | CSV/YAML 파일 직접 편집 | **유일한 입력 수단** |
| 향후 (웹 UI 후) | 웹 UI 기본 + 파일 보조 | **대량 임포트/익스포트** |

> KEPServerEX 방식과 동일: 기본은 GUI, 대량 작업은 CSV 익스포트 → 엑셀 편집 → 임포트

### 4.2 핵심 구조: Interface → Block → Block Map

현재의 3계층 구조를 유지한다.

```
Interface (인터페이스)                    ← 주로 호스트/연결 정보
│   1개의 외부 시스템 연결을 정의
│
└── Block (블록) [1:N]                   ← 논리 단위 / 프로세스 단위
    │   1개의 통신 동작을 정의 (읽기/쓰기, 주기, 트리거)
    │
    └── Block Map (태그 매핑) [1:M]      ← 각 블록의 태그 할당
            M이 수백~수천 개가 될 수 있음
```

- **Interface**: 어디에 연결할 것인가 (host, port, 인증 등)
- **Block**: 어떻게 통신할 것인가 (방향, 트리거, 주기 등)
- **Block Map**: 무엇을 읽고/쓸 것인가 (태그 ↔ 프로토콜 주소 매핑)

### 4.3 요구사항

| ID | 요구사항 | 우선순위 | 해결 대상 |
|----|---------|----------|-----------|
| R1 | **명시적 필드명**: `prop1~5` 대신 프로토콜별 의미 있는 이름 사용 | 높음 | P1 |
| R2 | **유연한 필드 수**: 프로토콜별로 필드 개수를 자유롭게 정의 | 높음 | P2 |
| R3 | **대량 태그 작성 용이**: 수백~수천 개 태그를 효율적으로 작성 | 높음 | P3 |
| R4 | **자기 설명**: 설정 파일 내에 주석, 필드 설명 포함 가능 | 중간 | P4 |
| R5 | **텍스트 기반**: Git diff로 변경 추적 가능 | 중간 | P5 |
| R6 | **과거 호환**: 기존 CSV 설정을 새 포맷으로 마이그레이션 가능 | 중간 | - |
| R7 | **작성 용이성**: 비개발자가 텍스트 에디터로 편집 가능 | 높음 | - |
| R8 | **템플릿/샘플**: 프로토콜별 샘플 파일 제공 | 중간 | - |
| R9 | **검증 가능**: 입력 오류를 로드 시점에 검출 | 중간 | - |
| R10 | **웹 UI 연동**: 향후 Django 웹 UI에서 입출력 가능 (최종 목표) | 높음 | - |
| R11 | **CSV 익스포트/임포트**: 웹 UI에서 대량 태그를 CSV로 내보내기/가져오기 | 높음 | P3 |
| R12 | **클라우드 동기화**: 설정을 원격 저장/복원 가능 | 낮음 | - |

---

## 5. 데이터 구조

### 5.1 계층 구조

```
인터페이스 (Interface)
│
├── 공통 필드
│   ├── id: 인터페이스 ID (유일)
│   ├── protocol: 프로토콜 코드
│   ├── host, port: 연결 주소
│   ├── timeout_s: 타임아웃
│   └── retry_s: 재시도 간격
│
├── 프로토콜별 연결 속성 (유연한 필드)
│   └── 예: path, server_name, client_id, database 등
│
├── 보안 속성 (유연한 필드)
│   └── 예: auth_type, username, password, certificate, private_key 등
│
└── 블록 (Block) [1:N]
    │
    ├── 공통 필드
    │   ├── id: 블록 ID (유일)
    │   ├── use: 사용 여부
    │   ├── rw: 방향 (ro, wo, wr)
    │   ├── trigger: 트리거 (cyc, onc, sub)
    │   ├── interval_s: 주기
    │   └── standby_s: 대기 시간
    │
    ├── 프로토콜별 블록 속성 (유연한 필드)
    │   └── 예: base_address, server_uri, namespace, qos 등
    │
    └── 태그 매핑 (Block Map) [1:M, M이 매우 클 수 있음]
        ├── tag: 태그 ID (databus 태그명)
        ├── index: 인덱스 타입 (v, q, t)
        └── 프로토콜별 주소 속성 (유연한 필드)
            └── 예: unit_id, func_code, address, data_type, node_id 등
```

### 5.2 프로토콜별 필드 정의

#### Modbus TCP Client (mtc)

```
Interface:
  - host, port

Block:
  - base_address: 0 또는 1 기반 주소 체계

Block Map:
  - unit_id: 슬레이브 ID
  - func_code: 펑션 코드 (1, 2, 3, 4, 5, 6, 15, 16)
  - address: 레지스터 주소
  - data_type: 데이터 타입 (int16, uint16, int32, float32 등)
  - bit_mask: 비트 마스크 (선택)
```

#### Modbus TCP Server (mts)

```
Interface:
  - host, port

Block:
  - unit_id: 슬레이브 ID
  - memory_area: 메모리 영역

Block Map:
  - unit_id: 슬레이브 ID
  - address: 레지스터 주소
```

#### OPC UA Client (ouc)

```
Interface:
  - host, port
  - path: OPC UA 경로 (예: "nodi/")
  - Security: auth_type, certificate, private_key, security_policy, encryption_mode

Block:
  - server_uri: 서버 URI (namespace)

Block Map:
  - node_id: 노드 ID
```

#### OPC UA Server (ous)

```
Interface:
  - host, port
  - path: OPC UA 경로
  - server_name: 서버 이름 (URI)
  - Security: auth_type, certificate, private_key, security_policy, encryption_mode

Block:
  - server_uri: 서버 URI (namespace)

Block Map:
  - identifier: 식별자
  - node_path: 노드 경로
  - writable: 쓰기 가능 여부
```

#### MQTT Client (mqc)

```
Interface:
  - host, port
  - Security: client_id, username, password

Block:
  - qos: QoS 레벨
  - retain: Retain 여부

Block Map:
  - topic: 토픽
```

#### Relation DB Client (rdc)

```
Interface:
  - host, port
  - driver: PostgreSQL, SQLite3 등
  - database: DB 경로 또는 이름
  - Security: username, password

Block:
  - query: SQL 쿼리문

Block Map:
  - (쿼리 결과 컬럼과 태그의 매핑)
```

#### Kafka Client (kfc)

```
Interface:
  - host, port (브로커 주소)

Block:
  - (프로듀서/컨슈머 설정)

Block Map:
  - topic: 토픽
```

### 5.3 태그 정의 (tag)

블록 매핑과 별도로 태그 자체를 정의하는 테이블.

```
tag (태그 정의)
├── tag: 태그 ID (PK, databus 태그명)
├── comment: 설명
└── init: 초기값
```

### 5.4 아카이브 정의 (arcv)

태그 데이터의 저장/정리 정책.

```
arcv (아카이브)
├── arcv: 아카이브 ID (PK)
├── schedule: 저장 주기 (cron 표현식)
├── revision: 리비전 주기
└── retention: 보관 기간

arcv_map (아카이브 ↔ 태그)
├── arcv: 아카이브 FK
└── tag: 태그 FK
```

---

## 6. 현재 방식의 핵심 한계 상세 분석

### 6.1 prop1~5 — 프로토콜별 의미 불투명 (P1)

**현재 CSV (의미를 알 수 없음):**
```csv
blck,tag,idx,prop1,prop2,prop3,prop4,prop5
mtc-w,mtc_i_wo0,v,1,6,100,uint16,
```

**원하는 형태 (의미가 명확함):**
```
mtc-w, mtc_i_wo0, v, unit_id=1, func_code=6, address=100, data_type=uint16
```

### 6.2 고정 5개 슬롯 (P2)

- 현재: `prop1, prop2, prop3, prop4, prop5` — 정확히 5개 고정
- Modbus는 5개를 거의 다 사용하지만, OPC UA Client는 1개(node_id)만 사용
- 새로운 공통 속성(예: `scale_a`, `scale_b`, `deadband`)을 추가하려면 전체 스키마 변경
- **필드 수가 프로토콜과 용도에 따라 자유로워야 함**

### 6.3 blck_map 대량 반복 (P3)

실제 운영 데이터 (blck_map.csv에서 발췌):

```csv
dsc-fems,elec-010-00_m_Va,v,,,,,
dsc-fems,elec-010-00_m_Vb,v,,,,,
dsc-fems,elec-010-00_m_Vc,v,,,,,
... (21개 메트릭 × 5대 = 105행, 이것이 3개 계열 반복 = ~315행)
```

- 전력계 1대당 21개 메트릭 (Va, Vb, Vc, Da, ..., Qa, Qb, Qc)
- 계열 010: 5대, 계열 011: 7대, 계열 100-01: 3대
- 총 15대 × 21메트릭 = **315행**이 거의 동일한 패턴
- 실제 현장에서는 수천 행까지 증가 가능
- **패턴이 있는 대량 태그를 효율적으로 표현할 수 있어야 함**

### 6.4 주석/설명 불가 (P4)

CSV에서는 다음이 불가능:
- 각 필드가 무엇을 의미하는지 인라인 설명
- 특정 행이 왜 이렇게 설정되었는지 메모
- 유효 값 범위, 단위 등의 안내

---

## 7. 포맷 역할 분석 및 최종 결론

### 7.1 비교표

| 기준 | CSV (현행) | YAML | JSON (DB 내부) |
|------|-----------|------|----------------|
| 비개발자 가독성 | 테이블형으로 OK | 들여쓰기 기반, 직관적 | 중괄호/따옴표 많아 불편 |
| 주석 지원 | `#` 행 주석 (비표준) | `#` 주석 | 불가 |
| 계층 구조 표현 | 불가 (파일 분리) | 네이티브 (들여쓰기) | 네이티브 (중괄호) |
| 임의 필드 수 | 헤더 변경 필요 | 자유 | 자유 |
| 대량 테이블 데이터 | **최강** | 약함 (장황) | 약함 |
| Python 파싱 | csv (표준 라이브러리) | PyYAML | json (표준 라이브러리) |
| 엑셀 연동 | 직접 호환 | 불가 | 불가 |
| Git diff | 좋음 | 좋음 | 보통 |
| DB 저장 | 그대로 저장 불가 | 그대로 저장 불가 | **SQLite JSON 함수로 쿼리 가능** |
| 웹 UI 연동 | 변환 필요 | 변환 필요 | **Django JSONField 네이티브** |

### 7.2 핵심 관찰

설정 데이터에는 **두 가지 성격**이 공존한다:

| 성격 | 해당 데이터 | 특성 | 적합한 포맷 |
|------|-----------|------|------------|
| 구조/설정 데이터 | interface, block | 항목 수 적음, 필드 많음, 프로토콜별로 다름 | JSON (DB), 웹 UI 폼 |
| 대량 매핑 데이터 | block_map, tag, arcv_map | 항목 수 매우 많음, 필드 적음, 반복 패턴 | CSV, 테이블형 |

→ **단일 포맷으로는 두 성격을 모두 만족시키기 어려움**

### 7.3 근본 제약 조건: 단일 CSV + 멀티 프로토콜 + 엑셀 편집

실무 현장에서는 한 사이트에 **여러 프로토콜**이 혼재한다 (예: Modbus + OPC UA + MQTT).
사용자는 `blck_map.csv` **하나의 파일**에서 모든 프로토콜의 태그를 편집해야 한다.

| 요구사항 | 설명 |
|---------|------|
| 단일 CSV 파일 | 프로토콜별 별도 CSV는 관리/편집이 불편 |
| 멀티 프로토콜 | 한 파일에 mtc, ouc, mqc 등이 공존 |
| 엑셀 편집 | 비개발자가 엑셀로 복사/붙여넣기, 연번 채우기 |

이 3가지를 동시에 만족하려면, **CSV 헤더를 프로토콜별 명시적 이름(`unit_id`, `node_id`)으로
바꿀 수 없다** — 프로토콜마다 필드 의미가 다르기 때문이다.

→ **결론: CSV에서는 `prop1~5` 범용 컬럼이 불가피하다.**

### 7.4 최종 결론: 3계층 포맷 전략

**YAML 기반 설계는 과잉 투자(over-engineering)이다.** 웹 UI가 곧 구현되므로,
파일 포맷에 투자하기보다 **DB 스키마 개선 + CSV 가독성 향상 + 웹 UI**에 집중한다.

| 계층 | 포맷 | 역할 |
|------|------|------|
| **DB (저장)** | JSON 컬럼 | `prop1~5` → `prop TEXT` (JSON). 유연한 필드, SQLite JSON 함수로 쿼리 |
| **CSV (교환)** | propN 컬럼 + 레전드 행 | 대량 편집용. 단일 파일, 멀티 프로토콜, 엑셀 호환 |
| **웹 UI (입력)** | 동적 폼 | JSON을 프로토콜별 라벨로 렌더링 (최종 목표) |

```
변환 흐름:

CSV 임포트: propN 컬럼 → JSON 변환 → DB 저장
CSV 익스포트: DB JSON → propN 컬럼 → CSV 파일
웹 UI:       JSON ↔ 동적 폼 필드 (Unit ID, Function Code 등)
```

---

## 8. 설계 방향: DB JSON + CSV propN + 웹 UI

### 8.1 핵심 전략

**DB는 JSON으로 유연하게, CSV는 propN으로 실용적으로, 웹 UI는 동적 폼으로 직관적으로.**

```
┌─────────────────────────────────────────────────────────────────┐
│  prot 테이블 (프로토콜 메타)  │  prot_prop 테이블 (필드 정의)     │
│  prot=mtc, dtyp=int, ...    │  prot=mtc, layer=map:            │
│  prot=ouc, dtyp=str, ...    │    pos=1 → unit_id  (Unit ID)    │
│                              │    pos=2 → func_code (Func Code) │
│                              │    pos=3 → address  (Address)    │
│                              │    pos=4 → data_type (Data Type) │
│                              │    pos=5 → bit_mask (Bit Mask)   │
└──────────────────────────────┴──────┬──────────────────┬────────┘
                                      │                  │
                                      ▼                  ▼
                          ┌───────────────────┐ ┌───────────────────┐
                          │  CSV (교환 포맷)    │ │ 웹 UI (입력 수단)  │
                          │                   │ │                   │
                          │ prop1,prop2,...    │ │ ┌─Unit ID────┐   │
                          │ 1,6,100,uint16,   │ │ │ 1          │   │
                          │                   │ │ ├─Func Code──┤   │
                          │ + 레전드 행:        │ │ │ 6          │   │
                          │ #[mtc] prop1=...  │ │ ├─Address────┤   │
                          │                   │ │ │ 100        │   │
                          └─────────┬─────────┘ └──────┬────────────┘
                                    │ 임포트       저장 │
                                    ▼                  ▼
                          ┌────────────────────────────────────────┐
                          │            SQLite DB (저장소)            │
                          │                                        │
                          │  prop TEXT = '{"unit_id":1,...}'        │
                          │  → json_extract(prop, '$.unit_id')     │
                          └────────────────────────────────────────┘
```

### 8.2 DB 스키마 (신규)

`prop1~5`, `secu1~5`를 **단일 `prop TEXT` (JSON) 컬럼**으로 통합한다.

#### intf (인터페이스)

```sql
CREATE TABLE intf (
    intf VARCHAR PRIMARY KEY,       -- 인터페이스 ID
    cmt  VARCHAR,                   -- 설명
    prot CHAR(3),                   -- 프로토콜 코드 (mtc, ouc, mqc 등)
    host VARCHAR,                   -- 호스트 주소
    port INTEGER,                   -- 포트 번호
    prop TEXT,                      -- JSON: 프로토콜별 연결 + 보안 속성 통합
    tout REAL,                      -- 타임아웃 (초)
    rtr  REAL                       -- 재시도 간격 (초)
);
```

**prop JSON 예시:**

```jsonc
// OPC UA Client
{"path": "nodi/", "auth_type": "anonymous",
 "certificate": "/root/edge/sys/nodi_cert.der",
 "private_key": "/root/edge/sys/nodi_pkey.pem"}

// MQTT Client
{"client_id": "nodi-edge-01", "username": "admin", "password": "secret"}

// Modbus TCP Client
{}  // 추가 속성 없음
```

#### blck (블록)

```sql
CREATE TABLE blck (
    blck VARCHAR PRIMARY KEY,       -- 블록 ID
    cmt  VARCHAR,                   -- 설명
    use  CHAR(1),                   -- 사용 여부 (Y/N)
    intf VARCHAR REFERENCES intf(intf),  -- 인터페이스 FK
    prop TEXT,                      -- JSON: 프로토콜별 블록 속성
    rw   CHAR(2),                   -- 방향 (ro, wo, wr)
    trig CHAR(3),                   -- 트리거 (cyc, onc, sub)
    tm   VARCHAR,                   -- 주기
    stby REAL                       -- 대기 시간 (초)
);
```

**prop JSON 예시:**

```jsonc
// Modbus TCP Client
{"base_address": 0}

// OPC UA Client
{"server_uri": "urn:freeopcua:python:server"}

// MQTT Client
{"qos": 1, "retain": false}
```

#### blck_map (태그 매핑)

```sql
CREATE TABLE blck_map (
    blck VARCHAR REFERENCES blck(blck),  -- 블록 FK
    tag  VARCHAR REFERENCES tag(tag),    -- 태그 FK
    idx  CHAR(2),                        -- 인덱스 타입 (v, q, t)
    prop TEXT                            -- JSON: 프로토콜별 태그 매핑 속성
);
```

**prop JSON 예시:**

```jsonc
// Modbus TCP Client
{"unit_id": 1, "func_code": 6, "address": 100, "data_type": "uint16"}

// OPC UA Client
{"node_id": "ns=2;s=rw0"}

// OPC UA Server
{"identifier": "Va", "path": "elec/010-00/m", "writable": true}
```

#### tag, arcv, arcv_map (변경 없음)

```sql
-- 기존과 동일
CREATE TABLE tag (
    tag  VARCHAR PRIMARY KEY,
    cmt  VARCHAR,
    init VARCHAR
);

CREATE TABLE arcv (
    arcv VARCHAR PRIMARY KEY,
    cmt  VARCHAR,
    sto  VARCHAR,
    rev  VARCHAR,
    ret  VARCHAR
);

CREATE TABLE arcv_map (
    arcv VARCHAR REFERENCES arcv(arcv),
    tag  VARCHAR REFERENCES tag(tag)
);
```

### 8.3 prot + prot_prop 테이블 (2테이블 분리)

기존 `prot` 테이블은 프로토콜 메타데이터와 필드 정의(comm_prop1~5, blck_prop1~5 등)가
**하나의 행에 가로로 나열**되어 있어 확장이 어렵다.

이를 **prot (메타데이터) + prot_prop (필드 정의)** 2테이블로 분리하여 정규화한다.

#### prot (프로토콜 메타데이터)

기존 `prot` 테이블에서 `comm_prop1~5`, `comm_secu1~5`, `blck_prop1~5`, `blck_map_prop1~5`
컬럼을 모두 제거하고 프로토콜 수준 메타데이터만 남긴다.

```sql
CREATE TABLE prot (
    prot      CHAR(3) PRIMARY KEY,
    cmt       VARCHAR,
    prot_dtyp CHAR(3) REFERENCES prot_dtyp(prot_dtyp),
    prot_dim  CHAR(2) REFERENCES prot_dim(prot_dim),
    prot_unit CHAR(4) REFERENCES prot_unit(prot_unit)
);
```

#### prot_prop (필드 정의 — 세로 정규화)

프로토콜별, 레이어별 필드 정의를 **1행 = 1필드**로 저장한다.

```sql
CREATE TABLE prot_prop (
    prot     CHAR(3) REFERENCES prot(prot),
    layer    VARCHAR NOT NULL,      -- 'intf', 'blck', 'map'
    pos      INTEGER NOT NULL,      -- propN 위치 (1~N), CSV 매핑용
    key      VARCHAR NOT NULL,      -- JSON 키 이름 (예: 'unit_id')
    label    VARCHAR NOT NULL,      -- 표시 라벨 (예: 'Unit ID')
    type     VARCHAR DEFAULT 'str', -- 데이터 타입 (str, int, float, bool)
    required CHAR(1) DEFAULT 'N',   -- 필수 여부 (Y/N)
    hint     VARCHAR,               -- 입력 힌트/설명
    PRIMARY KEY (prot, layer, pos)
);
```

#### 기존 대비 비교

```text
현재 (가로, 1테이블):
  prot | comm_prop1 | comm_prop2 | ... | blck_map_prop1 | blck_map_prop2 | ... (25+ 컬럼)
  mtc  | -          | -          |     | Unit ID        | Function Code  |
  ouc  | Path (URL) | -          |     | Node ID        | -              |

  → 라벨만 저장. type/required/hint 추가 불가. 5개 고정. "-" 가득.

신규 (세로, 2테이블):
  prot: mtc | Modbus TCP Client | int | 1d | blck    (메타데이터만)
  prot_prop:
    mtc | map  | 1 | unit_id   | Unit ID        | int | Y | 슬레이브 ID (1-247)
    mtc | map  | 2 | func_code | Function Code  | int | Y | 1,2,3,4,5,6,15,16
    mtc | map  | 3 | address   | Address        | int | Y | 레지스터 주소
    ...

  → 필드 수 무제한. 메타데이터 자유 확장. 필요한 행만 존재.
```

#### prot_prop 데이터 예시

```text
prot | layer | pos | key          | label          | type  | required | hint
─────┼───────┼─────┼──────────────┼────────────────┼───────┼──────────┼───────────────────────
mtc  | blck  | 1   | base_addr    | 0/1-based      | int   | N        | 0 또는 1 기반 주소
mtc  | map   | 1   | unit_id      | Unit ID        | int   | Y        | 슬레이브 ID (1-247)
mtc  | map   | 2   | func_code    | Function Code  | int   | Y        | 1,2,3,4,5,6,15,16
mtc  | map   | 3   | address      | Address        | int   | Y        | 레지스터 주소
mtc  | map   | 4   | data_type    | Data Type      | str   | Y        | int16,uint16,float32,...
mtc  | map   | 5   | bit_mask     | Bit Mask       | str   | N        | 비트 마스크
ouc  | intf  | 1   | path         | Path           | str   | Y        | URL 경로
ouc  | intf  | 2   | auth_type    | Auth Type      | str   | Y        | anonymous,certificate
ouc  | intf  | 3   | certificate  | Certificate    | str   | N        | 인증서 파일 경로
ouc  | intf  | 4   | private_key  | Private Key    | str   | N        | 개인키 파일 경로
ouc  | blck  | 1   | server_uri   | Namespace      | str   | Y        | 서버 URI
ouc  | map   | 1   | node_id      | Node ID        | str   | Y        | OPC UA 노드 ID
mqc  | intf  | 1   | username     | Username       | str   | N        | MQTT 사용자
mqc  | intf  | 2   | password     | Password       | str   | N        | MQTT 비밀번호
mqc  | blck  | 1   | qos          | QoS            | int   | N        | 0, 1, 2
mqc  | blck  | 2   | retain       | Retain         | bool  | N        | true/false
mqc  | map   | 1   | topic        | Topic          | str   | Y        | MQTT 토픽
```

#### prot_prop의 3가지 역할

1. **CSV ↔ JSON 변환**: `pos`로 propN 위치 결정, `key`로 JSON 키 매핑
2. **웹 UI 렌더링**: `label`로 폼 필드 라벨, `type`으로 입력 위젯 결정, `hint`로 도움말
3. **검증**: `required`로 필수 필드 체크, `type`으로 타입 검증

### 8.4 CSV 포맷 (레전드 행 메커니즘)

CSV 파일은 기존 `propN` 컬럼을 유지하되, **레전드(legend) 행**으로 각 propN의 의미를 표기한다.

#### blck_map.csv 예시

```csv
#[mtc] prop1=unit_id(Unit ID), prop2=func_code(Function Code), prop3=address(Address), prop4=data_type(Data Type), prop5=bit_mask(Bit Mask)
#[ouc] prop1=node_id(Node ID)
#[ous] prop1=identifier(Identifier), prop2=path(Path), prop3=writable(Writable)
blck,tag,idx,prop1,prop2,prop3,prop4,prop5
mtc-w,mtc_i_wo0,v,1,6,100,uint16,
mtc-w,mtc_i_wo1,v,1,6,101,uint16,
ouc-a,ouc_i_rw0,v,ns=2;s=rw0,,,,
ous-f,elec-010-00_m_Va,v,Va,elec/010-00/m,true,,
```

**레전드 행 규칙:**

- `#` 으로 시작 (CSV 주석 행)
- `[prot]` 로 프로토콜 지정
- `propN=json_key(표시라벨)` 형식
- CSV 로더가 파싱하여 propN → JSON 변환 시 참조
- 레전드 행이 없으면 `prot_prop` 테이블에서 매핑 정보를 가져옴

#### intf.csv 예시

```csv
#[ouc] prop1=path(Path), prop2=auth_type(Auth Type), prop3=certificate(Certificate), prop4=private_key(Private Key)
#[mqc] prop1=client_id(Client ID), prop2=username(Username), prop3=password(Password)
intf,cmt,prot,host,port,prop1,prop2,prop3,prop4,prop5,tout,rtr
ouc,,ouc,localhost,4841,nodi/,anonymous,/root/edge/sys/nodi_cert.der,/root/edge/sys/nodi_pkey.pem,,5.0,10.0
mtc,,mtc,0.0.0.0,502,,,,,,,5.0,10.0
mqc,,mqc,broker.local,1883,nodi-edge-01,admin,secret,,,5.0,10.0
```

> **기존 CSV 대비 변경점**: 레전드 행 추가만으로 자기 설명 가능 (P4 해결).
> CSV 구조 자체는 변경 없으므로 기존 엑셀 워크플로우 그대로 유지.

### 8.5 변환 흐름

#### CSV → DB (임포트)

```python
# 1. 레전드 행 파싱 → 프로토콜별 propN→key 매핑 구성
# 2. (레전드 없으면) prot_prop 테이블에서 매핑 로드
# 3. 데이터 행 읽기, 각 행의 prot 확인 (blck_map은 blck→intf→prot 조인)
# 4. propN 값을 JSON으로 변환
# 5. DB에 저장

def load_mapping(db, prot_code: str, layer: str) -> dict:
    """prot_prop에서 pos→key 매핑 로드"""
    rows = db.execute(
        "SELECT pos, key, type FROM prot_prop WHERE prot = ? AND layer = ? ORDER BY pos",
        (prot_code, layer)).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}  # {1: ('unit_id', 'int'), ...}

def propn_to_json(row: dict, mapping: dict) -> str:
    """propN 컬럼들을 JSON 문자열로 변환 (타입 캐스팅 포함)"""
    result = {}
    for pos, (key, typ) in mapping.items():
        val = row.get(f"prop{pos}")
        if val:
            if typ == 'int':
                val = int(val)
            elif typ == 'float':
                val = float(val)
            elif typ == 'bool':
                val = val.lower() in ('true', '1', 'yes')
            result[key] = val
    return json.dumps(result)
```

#### DB → CSV (익스포트)

```python
# 1. prot_prop 테이블에서 해당 프로토콜의 매핑 로드
# 2. DB의 JSON prop을 propN 컬럼으로 분해
# 3. 레전드 행 자동 생성 (사용된 프로토콜만)
# 4. CSV 파일 출력

def json_to_propn(json_str: str, mapping: dict) -> dict:
    """JSON을 propN 컬럼들로 변환"""
    data = json.loads(json_str) if json_str else {}
    result = {}
    for pos, (key, typ) in mapping.items():
        result[f"prop{pos}"] = str(data.get(key, ""))
    return result

def generate_legend(db, prot_code: str, layer: str) -> str:
    """prot_prop 기반 레전드 행 자동 생성"""
    rows = db.execute(
        "SELECT pos, key FROM prot_prop WHERE prot = ? AND layer = ? ORDER BY pos",
        (prot_code, layer)).fetchall()
    parts = [f"prop{r[0]}={r[1]}" for r in rows]
    return f"#[{prot_code}] {', '.join(parts)}"
```

#### 웹 UI ↔ DB

```python
# Django 모델에서 JSONField 사용
class BlockMap(models.Model):
    blck = models.ForeignKey(Block, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    idx = models.CharField(max_length=2)
    prop = models.JSONField(default=dict)

# 웹 UI에서 prot_prop 테이블 기반 동적 폼 렌더링
fields = ProtProp.objects.filter(prot=prot_code, layer='map').order_by('pos')
for field in fields:
    # field.label → 폼 필드 라벨
    # field.type → 입력 위젯 (text, number, checkbox)
    # field.hint → placeholder 또는 tooltip
    # field.required → 필수 표시
```

---

## 9. 구체적 예시: 현재 → 신규

### 9.1 intf (인터페이스) 변환 예시

**현재 DB (prop1~5, secu1~5):**

```text
intf | prot | host      | port | prop1  | prop2     | prop3                          | prop4                           | secu1~5
ouc  | ouc  | localhost | 4841 | nodi/  | anonymous | /root/edge/sys/nodi_cert.der   | /root/edge/sys/nodi_pkey.pem    | ...
mtc  | mtc  | 0.0.0.0  | 502  |        |           |                                |                                 |
```

**신규 DB (prop JSON):**

```text
intf | prot | host      | port | prop                                                                              | tout | rtr
ouc  | ouc  | localhost | 4841 | {"path":"nodi/","auth_type":"anonymous","certificate":"...cert.der","private_key":"...pkey.pem"} | 5.0  | 10.0
mtc  | mtc  | 0.0.0.0  | 502  | {}                                                                                | 5.0  | 10.0
```

**CSV (변경 최소화 — 레전드 행 추가):**

```csv
#[ouc] prop1=path, prop2=auth_type, prop3=certificate, prop4=private_key
intf,cmt,prot,host,port,prop1,prop2,prop3,prop4,prop5,tout,rtr
ouc,,ouc,localhost,4841,nodi/,anonymous,/root/edge/sys/nodi_cert.der,/root/edge/sys/nodi_pkey.pem,,5.0,10.0
mtc,,mtc,0.0.0.0,502,,,,,,,5.0,10.0
```

### 9.2 blck_map (태그 매핑) 변환 예시

**현재 CSV (의미 불투명):**

```csv
blck,tag,idx,prop1,prop2,prop3,prop4,prop5
mtc-w,mtc_i_wo0,v,1,6,100,uint16,
mtc-w,mtc_i_wo1,v,1,6,101,uint16,
ouc-a,ouc_i_rw0,v,ns=2;s=rw0,,,,
```

**신규 CSV (레전드 행으로 의미 명확):**

```csv
#[mtc] prop1=unit_id, prop2=func_code, prop3=address, prop4=data_type, prop5=bit_mask
#[ouc] prop1=node_id
blck,tag,idx,prop1,prop2,prop3,prop4,prop5
mtc-w,mtc_i_wo0,v,1,6,100,uint16,
mtc-w,mtc_i_wo1,v,1,6,101,uint16,
ouc-a,ouc_i_rw0,v,ns=2;s=rw0,,,,
```

**신규 DB (JSON 저장):**

```text
blck  | tag         | idx | prop
mtc-w | mtc_i_wo0   | v   | {"unit_id":1,"func_code":6,"address":100,"data_type":"uint16"}
mtc-w | mtc_i_wo1   | v   | {"unit_id":1,"func_code":6,"address":101,"data_type":"uint16"}
ouc-a | ouc_i_rw0   | v   | {"node_id":"ns=2;s=rw0"}
```

**웹 UI (프로토콜별 동적 폼):**

```text
┌─ 블록: mtc-w ──────────────────────────────────┐
│ 태그: mtc_i_wo0                                 │
│ ┌─Unit ID──────┐ ┌─Function Code─┐             │
│ │ 1            │ │ 6             │             │
│ └──────────────┘ └───────────────┘             │
│ ┌─Address──────┐ ┌─Data Type─────┐             │
│ │ 100          │ │ uint16    ▼   │             │
│ └──────────────┘ └───────────────┘             │
└─────────────────────────────────────────────────┘
```

### 9.3 한계 해결 매핑

| 한계 (섹션 6) | 해결 방법 |
|------|------|
| P1. prop1~5 의미 불투명 | DB: JSON 키로 의미 명확, CSV: 레전드 행, 웹 UI: 라벨 표시 |
| P2. 고정 5개 슬롯 | DB: JSON이므로 필드 수 무제한. CSV: propN 컬럼 추가 가능 |
| P3. blck_map 대량 반복 | 웹 UI CSV 임포트로 엑셀 대량 편집 지원 (구조적 해결은 웹 UI 몫) |
| P4. 자기 설명 불가 | CSV: 레전드 행, 웹 UI: 동적 라벨/힌트 |
| P5. Git diff 비친화적 | CSV 파일 자체를 Git 추적 (DB는 런타임 전용) |

---

## 10. 로드맵

### 10.1 단계별 로드맵

```text
Phase 1 (현재)              Phase 2 (단기)              Phase 3 (장기)
CSV 기반 + DB 개선           웹 UI + CSV 보조             웹 UI + 클라우드
───────────────────      ───────────────────       ───────────────────
[CSV 파일 편집]            [Django 웹 UI]              [웹 UI]
  + 레전드 행                ├── 폼 입력 (기본)          ├── 폼 입력 (기본)
      │                    ├── CSV 임포트 (대량)       ├── CSV 임포트
      ▼                    └── CSV 익스포트            └── 클라우드 동기화
[csv_loader]                     │
  propN → JSON                   ▼
      │                    [SQLite DB]
      ▼                     prop TEXT (JSON)
[SQLite DB]
 prop TEXT (JSON)
```

### 10.2 Phase 1 — CSV + DB JSON (현재)

기존 CSV 편집 워크플로우를 유지하면서 DB 내부를 JSON으로 전환하는 단계.

**작업 항목:**

1. DB 스키마 전환: `prop1~5`, `secu1~5` → `prop TEXT` (JSON)
2. `prot` 테이블 분리: `prot` (메타데이터) + `prot_prop` (필드 정의, 세로 정규화)
3. `csv_loader` 수정: `prot_prop` 참조하여 propN → JSON 변환
4. CSV 레전드 행 도입: `#[prot] prop1=key_name` 형식
5. 기존 CSV 파일에 레전드 행 추가

**이 단계의 핵심:**

- 사용자 입장에서는 **기존과 동일한 CSV 편집 경험**
- DB 내부만 JSON으로 바뀌어 **향후 웹 UI 전환이 자연스러움**
- 레전드 행으로 CSV의 자기 설명 문제(P4) 부분 해결

### 10.3 Phase 2 — 웹 UI + CSV 보조 (단기 목표)

Django 기반 웹 UI가 **기본 입력 수단**이 되는 단계.

**기본 워크플로우 (소량 설정):**

1. Django 웹 UI 접속
2. 폼으로 인터페이스/블록/태그 입력 (`prot_prop` 테이블 기반 동적 폼)
3. DB에 JSON으로 저장
4. 앱 재시작 또는 설정 리로드

**대량 입력 워크플로우 (KEPServerEX 방식):**

1. 웹 UI에서 기존 태그 매핑을 CSV로 익스포트
2. 사용자가 엑셀/스프레드시트로 CSV를 열어 대량 편집
   - 행 복사/붙여넣기, 연번 자동 채우기, 주소 일괄 수정 등
3. 편집한 CSV를 웹 UI에서 임포트
4. 검증 결과 확인 → 적용

> 이 워크플로우에서 CSV는 "엑셀과 웹 UI 사이의 교환 포맷" 역할을 한다.
> CSV 레전드 행과 `prot_prop` 테이블 기반 검증으로 입력 오류를 조기에 검출한다.

### 10.4 Phase 3 — 웹 UI + 클라우드 (장기 목표)

1. Phase 2의 모든 기능 포함
2. 로컬 설정을 클라우드에 자동/수동 동기화
3. 클라우드에서 다중 기기 설정 일괄 관리
4. 원격 설정 배포 (클라우드 → 엣지 기기)

### 10.5 포맷별 역할 정리

| 포맷 | Phase 1 역할 | Phase 2+ 역할 |
| --- | --- | --- |
| **CSV** | **기본 입력 포맷** (엑셀 편집) | 대량 태그 익스포트/임포트 (엑셀 연동) |
| **JSON** | DB 내부 저장 포맷 (prop 컬럼) | DB 내부 저장 + 웹 UI 네이티브 연동 |
| **SQLite** | 런타임 저장소 | 런타임 저장소 (Django ORM 관리) |

---

## 11. 저장 경로

```text
/home/nodi/nodi-edge-data/
├── backup/                  # 클라우드 동기화 대상
├── config/
│   ├── intf.csv             # 인터페이스 정의
│   ├── blck.csv             # 블록 정의
│   ├── blck_map.csv         # 태그 매핑
│   ├── tag.csv              # 태그 정의
│   ├── arcv.csv             # 아카이브 설정
│   └── arcv_map.csv         # 아카이브 ↔ 태그 매핑
├── data/
│   └── snapshots/           # databus 스냅샷
├── db/
│   └── edge.db              # SQLite (런타임 저장소, JSON prop)
└── log/
```

---

## 12. 처리 파이프라인

### 12.1 Phase 1 — CSV → DB (JSON)

```text
[CSV 파일 (propN 컬럼)]
     │
     ▼
csv_loader
  ├── 레전드 행 파싱 (#[prot] prop1=key...)
  ├── prot_prop 테이블 참조 (레전드 없을 때 fallback)
  ├── propN → JSON 변환 (prot_prop.type 기반 타입 캐스팅)
  └── 검증 (required 필드, 타입 체크)
     │
     ▼
[SQLite DB]
  intf.prop = '{"path":"nodi/","auth_type":"anonymous",...}'
  blck.prop = '{"base_address":0}'
  blck_map.prop = '{"unit_id":1,"func_code":6,"address":100,...}'
     │
     ▼
[앱이 DB 읽기]
  json_extract(prop, '$.unit_id') → 1
```

### 12.2 Phase 2 — 웹 UI + CSV 임포트/익스포트

```text
┌──────────────────────────────────────────────┐
│              Django 웹 UI                     │
│          (기본 입력 수단, 최종 목표)            │
└──────┬────────────────┬──────────────────────┘
       │                │
       ▼                ▼
  [동적 폼 입력]   [CSV 임포트/익스포트]
  prot_prop 기반      propN ↔ JSON 변환
  라벨/힌트 렌더링     레전드 행 자동 생성
       │                │
       ▼                ▼
┌──────────────────────────────────────────────┐
│        Django ORM / SQLite DB                 │
│        prop = JSONField (네이티브 JSON)        │
└──────────────────────────────────────────────┘
       │
       ▼
  [앱이 DB 읽기]
```

---

## 13. 결정 사항 및 미결정 사항

### 13.1 결정 사항

| 항목 | 결정 내용 | 근거 |
| --- | --- | --- |
| DB 포맷 | `prop1~5` → `prop TEXT` (JSON) | 유연한 필드 수, SQLite JSON 함수, Django JSONField 연동 |
| CSV 포맷 | propN 컬럼 유지 + 레전드 행 | 단일 파일 + 멀티 프로토콜 + 엑셀 호환 제약 |
| 최종 입력 수단 | Django 웹 UI | KEPServerEX 방식: GUI 기본 + CSV 대량 보조 |
| intf 통합 | `prop1~5` + `secu1~5` → `prop TEXT` 하나로 | 연결 속성과 보안 속성을 단일 JSON으로 관리 |
| YAML 설계 | 불채택 | 웹 UI가 곧 구현되므로 과잉 투자. CSV + JSON으로 충분 |
| prot 테이블 | `prot` (메타) + `prot_prop` (필드 정의) 2테이블 분리 | 세로 정규화로 필드 수 무제한. CSV↔JSON + 웹 UI + 검증 3역할 |

### 13.2 미결정 사항

#### propN 컬럼 수 확장

- [ ] 기존 5개(`prop1~5`) 유지
- [ ] 필요 시 `prop6~10` 등으로 확장
- [ ] DB에는 영향 없음 (JSON이므로). CSV 헤더만 변경

#### 검증 방식

- [ ] `prot_prop` 테이블 기반 검증 (required, type 체크)
- [ ] 추가 검증 규칙 정의 방법 (정규식, 범위, enum 등)
- [ ] 검증 에러 리포트 포맷

#### CSV 레전드 행 상세 규격

- [ ] 레전드 행 파싱 규칙 확정 (`#[prot] propN=key(label)` vs `#[prot] propN=key`)
- [ ] 레전드 행 없을 때의 fallback 동작 (`prot_prop` 테이블만 참조)
- [ ] 다중 프로토콜이 같은 propN에 다른 타입을 요구할 때의 처리

#### Django 연동 상세

- [ ] Django 모델 설계 (JSONField 사용 확정)
- [ ] 웹 UI 동적 폼 렌더링 방식 (서버사이드 vs 클라이언트사이드)
- [ ] CSV 임포트 시 충돌 처리 (기존 데이터와 중복 시 덮어쓰기 vs 병합)

#### 마이그레이션

- [ ] 기존 DB (`prop1~5`) → 신규 DB (`prop TEXT` JSON) 마이그레이션 스크립트
- [ ] 기존 CSV 파일에 레전드 행 자동 추가 도구
- [ ] 앱 코드의 `prop1~5` 직접 참조 → JSON 기반 접근으로 전환
