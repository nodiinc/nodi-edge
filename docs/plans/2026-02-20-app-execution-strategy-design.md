# 인터페이스 앱 실행 전략 설계

> 날짜: 2026-02-20
> 상태: 승인됨


## 1. 프로세스 모델: Connection 단위

하나의 연결(connection) = 하나의 독립 OS 프로세스.

- 같은 연결의 복수 블록은 단일 프로세스 내에서 `PeriodicTimer`로 스케줄링
- 각 프로세스는 완전히 독립된 Python 인터프리터 (systemd 서비스)
- 예: Modbus TCP에서 PLC 1대(IP:포트) = 1 프로세스

```
ne-intf-mtc-01.service  → python3 -m nodi_edge_intf.mtc --conn-id=mtc-01
  ├─ Block: read_holding (100ms 주기)
  ├─ Block: read_input (500ms 주기)
  └─ Block: write_coils (on-demand)
```

### 왜 Connection 단위인가

| 기준 | Block 단위 | Connection 단위 |
|------|-----------|----------------|
| 프로세스 수 | 블록 수만큼 (많음) | 연결 수만큼 (적음) |
| TCP 연결 | 블록마다 별도 소켓 | 연결당 하나 공유 |
| 장치 동시접속 제한 | 위반 가능 (PLC는 보통 1~4개) | 안전 |
| 맥락 공유 | 불가 (같은 장치 데이터 분산) | 가능 (장치 단위 통합) |
| 구현 복잡도 | 낮음 | 중간 (블록 스케줄링 필요) |


## 2. 실행 모델: 동기 단일 루프

기본은 **동기 단일 이벤트 루프** + `PeriodicTimer` (블록별 독립 주기).

- 하나의 TCP 연결에서 I/O는 본질적으로 순차적 → 스레드 불필요
- 동일 소켓에 스레드를 쓰면 락 직렬화로 오히려 오버헤드만 증가
- OPC UA (asyncua) 등 비동기 프로토콜은 `asyncio` 이벤트 루프 사용 가능하도록 프레임워크 설계

```
[ Block A: 100ms ] → I/O → [ Block B: 500ms ] → I/O → [ Block C: on-demand ] → ...
         ↑                          ↑
    PeriodicTimer              PeriodicTimer
```


## 3. 프로세스 관리: systemd

Supervisor가 `.service` 파일을 동적으로 생성/관리.

- systemd가 Supervisor 자체를 관리 (`ne-supervisor.service`)
- Supervisor가 각 InterfaceApp의 `.service` 파일 생성 → `systemctl start/stop/restart`
- 서비스 네이밍: `ne-intf-{conn_id}.service`

```ini
# /etc/systemd/system/ne-intf-mtc-01.service (자동 생성)
[Unit]
Description=Nodi Edge Interface - mtc-01
After=ne-supervisor.service

[Service]
Type=simple
User=root
ExecStart=/root/.venv/bin/python3 -m nodi_edge_intf.mtc --conn-id=mtc-01
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### systemd의 장점

- 완전한 프로세스 격리 (진정한 MSA)
- 자동 재시작 (`Restart=always`)
- 통합 로깅 (`journalctl -u ne-intf-mtc-01`)
- 리소스 제한 가능 (`MemoryMax`, `CPUQuota`)
- Supervisor가 죽어도 앱은 계속 실행


## 4. 설정 전달: CLI 인자

앱 시작 시 `--conn-id`를 CLI 인자로 전달. 앱이 DB에서 직접 조회.

```
Supervisor → systemctl start ne-intf-mtc-01
mtc-01 앱 시작 → argparse로 --conn-id=mtc-01 파싱
             → DB.select_connection(conn_id="mtc-01") → 연결 정보 (IP, 포트 등)
             → DB.select_blocks(conn_id="mtc-01") → 블록 목록
             → 설정 적용 후 EXECUTE 상태 진입
```


## 5. 설정 변경 감지: 시스템 태그 기반 (이벤트 푸시)

**DB 폴링 없음.** 변경 주체가 시스템 태그값 변경으로 이벤트 전달.

### 핵심 원칙

- DB는 SoT (Source of Truth) — 앱이 설정을 적용할 때 DB에서 읽음
- 변경 감지는 TagBus 시스템 태그의 값 변경으로 수행
- TagBus가 태그 동기화/누락 방어를 보장하므로 별도 유실 방지 불필요

### 시스템 태그 규약

```
/system/{app_id}/config_reload     ← 설정 재로드 요청 (블록 변경 등)
/system/supervisor/conn_added      ← 새 연결 추가 알림
/system/supervisor/conn_removed    ← 연결 삭제 알림
```

### 변경 흐름

```
변경 주체 (CSV Loader / Web UI)
  │
  ├─① DB에 설정 쓰기
  │
  └─② TagBus 시스템 태그 값 변경
       │
       ├─ /system/mtc-01/config_reload = <timestamp>
       │   → mtc-01 앱이 on_tags_update로 수신
       │   → DB 조회 → 변경 유형 판단 → 적용
       │
       ├─ /system/supervisor/conn_added = "opcua-02"
       │   → Supervisor가 수신
       │   → .service 생성 → systemctl start
       │
       └─ /system/supervisor/conn_removed = "mtc-03"
            → Supervisor가 수신
            → systemctl stop → .service 삭제
```


## 6. 설정 변경 시 재구성 전략: 변경 유형별

| 변경 유형 | 처리 방식 | 메커니즘 |
|-----------|-----------|----------|
| 블록 추가/삭제/수정 | **핫 리로드** | CONFIGURE 상태로 전환, 설정 재로드 후 EXECUTE 복귀 |
| 연결 정보 변경 (IP/포트) | **앱 재시작** | 자체 판단 후 `sys.exit()` → systemd `Restart=always`로 자동 재시작 |
| 새 연결 추가 | **서비스 생성** | Supervisor가 .service 생성 + systemctl start |
| 연결 삭제 | **서비스 제거** | Supervisor가 systemctl stop + .service 삭제 |

### 핫 리로드 시 FSM 전이

```
EXECUTE → (config_reload 태그 감지) → CONFIGURE → (설정 재로드) → CONNECT → EXECUTE
```


## 7. 전체 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│                        변경 주체                                  │
│         CSV Loader / Web UI (Django) / CLI                       │
└───────┬──────────────────────────────┬───────────────────────────┘
        │ ① DB 쓰기                    │ ② 시스템 태그 변경
        ▼                              ▼
  ┌──────────┐                 ┌──────────────┐
  │ SQLite   │                 │   TagBus     │
  │  (SoT)   │◄───── ③ 조회 ──│              │
  └──────────┘                 └──┬───────┬───┘
                                  │       │
              ┌───────────────────┤       ├───────────────────┐
              ▼                   ▼       ▼                   ▼
    ┌─────────────────┐  ┌────────────┐  ┌────────────┐
    │   Supervisor    │  │  mtc-01    │  │  opcua-01  │  ...
    │  (systemd 서비스)│  │  (systemd) │  │  (systemd) │
    │                 │  │            │  │            │
    │ 구독:           │  │ 구독:      │  │ 구독:      │
    │ conn_added     │  │ config_    │  │ config_    │
    │ conn_removed   │  │ reload     │  │ reload     │
    │                 │  │            │  │            │
    │ 수행:           │  │ 수행:      │  │ 수행:      │
    │ .service 생성   │  │ DB 조회    │  │ DB 조회    │
    │ systemctl 제어  │  │ 핫 리로드  │  │ 핫 리로드  │
    └─────────────────┘  └────────────┘  └────────────┘
```


## 8. 결정 사항 요약

| # | 주제 | 결정 |
|---|------|------|
| 1 | 실행 단위 | Connection 단위 (1 conn = 1 process) |
| 2 | 실행 모델 | 동기 단일 루프 + PeriodicTimer (비동기 옵션) |
| 3 | 프로세스 관리 | systemd (.service 파일 동적 생성) |
| 4 | 설정 전달 | CLI 인자 (--conn-id) → DB 직접 조회 |
| 5 | 변경 감지 | 시스템 태그 기반 이벤트 푸시 (DB 폴링 없음) |
| 6 | 재구성 전략 | 변경 유형별 (블록→핫 리로드, 연결→재시작) |
