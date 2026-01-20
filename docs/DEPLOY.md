# nodi-edge 배포 가이드

## 사전 요구사항

- Python 3.9+
- pip
- git

---

## 1. 전체 배포

모든 앱을 포함한 전체 프로젝트 배포:

```bash
# 1. 프로젝트 클론
git clone https://github.com/nodiinc/nodi-edge.git
cd nodi-edge

# 2. 의존성 및 프로젝트 설치
./nodi-edge-setup.sh
```

setup 스크립트가 자동으로:
- `nodi-libs` 클론 및 설치
- `nodi-databus` 클론 및 설치
- `nodi-edge` 설치

---

## 2. 특정 앱만 배포 (Sparse Checkout)

필요한 앱만 선택적으로 배포:

```bash
# 1. Sparse 모드로 클론 (메타데이터만 받음)
git clone --filter=blob:none --sparse https://github.com/nodiinc/nodi-edge.git
cd nodi-edge

# 2. 필요한 디렉토리만 체크아웃
git sparse-checkout set src apps/monitor nodi-edge-setup.sh pyproject.toml

# 3. 설치
./nodi-edge-setup.sh
```

### 여러 앱 선택

```bash
git sparse-checkout set src apps/monitor apps/modbus_tcp_client nodi-edge-setup.sh pyproject.toml
```

### 현재 sparse-checkout 목록 확인

```bash
git sparse-checkout list
```

### 앱 추가

```bash
git sparse-checkout add apps/opc_ua_server
```

---

## 3. 버전 관리

### 특정 버전 배포

```bash
# 태그로 버전 지정
git clone --branch v1.0.0 https://github.com/nodiinc/nodi-edge.git

# 또는 클론 후 체크아웃
git checkout v1.0.0
```

### Sparse Checkout + 특정 버전

```bash
git clone --filter=blob:none --sparse --branch v1.0.0 https://github.com/nodiinc/nodi-edge.git
cd nodi-edge
git sparse-checkout set src apps/monitor nodi-edge-setup.sh pyproject.toml
```

---

## 4. 업데이트

### 전체 업데이트

```bash
cd nodi-edge
git pull
```

### Sparse Checkout 업데이트

```bash
cd nodi-edge
git pull
# sparse-checkout 설정은 유지됨
```

---

## 디렉토리 구조

```
/your/path/
├── nodi-libs/          # 자동 클론됨
├── nodi-databus/       # 자동 클론됨
└── nodi-edge/
    ├── src/nodi_edge/  # 프레임워크
    ├── apps/
    │   ├── test/
    │   ├── monitor/
    │   └── ...
    ├── nodi-edge-setup.sh
    └── pyproject.toml
```

---

## 앱 실행

```bash
# 개별 앱 실행
python apps/monitor/main.py
python apps/test/main.py
```
