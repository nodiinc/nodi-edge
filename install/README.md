# Install Scripts Guide

nodi-edge 설치 스크립트 작성 규칙입니다.

## 파일 구조

```
install/
├── tool.py              # 출력 유틸리티 (head, desc, info, warn, fail, done)
├── install_serial.py    # 시리얼 번호 설치
├── install_users.py     # 사용자 계정 설치
└── README.md            # 이 문서
```

## 스크립트 작성 규칙

### 1. 함수 없이 스크립트처럼 작성

함수로 감싸지 말고, 위에서 아래로 쭉 흐르는 스크립트 형태로 작성합니다.

```python
# ✅ 좋은 예
if os.geteuid() != 0:
    fail("This script must be run as root.")
    sys.exit(1)

IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
IDENTITY_FILE.write_text(content)

# ❌ 나쁜 예
def main():
    check_root()
    install()

if __name__ == "__main__":
    main()
```

### 2. 섹션 구분

굵은 선(━━━━) 스타일은 **상위 섹션** (Constants, Helper Functions, Installation)에 사용합니다.

```python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IDENTITY_DIR = Path("/etc/nodi")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Installation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

head("Install Serial Number")
```

대시(────) 스타일은 **하위 섹션** (Installation 내부의 세부 단계)에 사용합니다.

```python
# ────────────────────────────────────────────────────────────
# Check Prerequisites
# ────────────────────────────────────────────────────────────

desc("Check Prerequisites")
...

# ────────────────────────────────────────────────────────────
# Check Existing
# ────────────────────────────────────────────────────────────

desc("Check Existing")
...
```

### 3. 출력은 tool.py 사용

로직과 출력을 분리합니다.

```python
from tool import head, desc, info, warn, fail, done

head("Install Serial Number")      # 파일 헤더 (굵은 박스, Cyan + Bold)
desc("Install")                    # 섹션 설명 (얇은 박스, Cyan)
info(f"{IDENTITY_FILE}")           # 일반 정보
warn("File already exists")        # 경고 (Yellow)
fail("Permission denied")          # 실패 (Red)
done("Installation complete")      # 완료 (Green)
```

### 4. 멱등성 (Idempotent)

여러 번 실행해도 동일한 결과가 나와야 합니다.

```python
# ✅ 좋은 예: 디렉토리 생성
IDENTITY_DIR.mkdir(parents=True, exist_ok=True)

# ✅ 좋은 예: 읽기 전용 파일 덮어쓰기
if IDENTITY_FILE.exists():
    os.chmod(IDENTITY_FILE, 0o644)  # 쓰기 가능하게 변경
IDENTITY_FILE.write_text(content)
os.chmod(IDENTITY_FILE, 0o444)      # 다시 읽기 전용으로

# ✅ 좋은 예: 사용자 존재 확인
if user_exists(USER_NODI):
    info(f"User '{USER_NODI}' already exists. Skipping.")
else:
    run(["useradd", "-m", "-s", "/bin/bash", USER_NODI])
```

### 5. root 권한 확인

설치 스크립트는 대부분 root 권한이 필요합니다.

```python
if os.geteuid() != 0:
    fail("This script must be run as root.")
    info("Usage: sudo python3 install_xxx.py")
    sys.exit(1)
```

### 6. 기존 설정 덮어쓰기 확인

중요한 설정을 덮어쓸 때는 사용자 확인을 받습니다.

```python
if IDENTITY_FILE.exists():
    old_value = read_existing_value()
    warn(f"Already exists: {old_value}")
    confirm = input("  Overwrite? [y/N]: ").strip().lower()
    if confirm != "y":
        info("Aborted.")
        sys.exit(0)
```

### 7. 파일 헤더

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install description."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from tool import head, desc, info, warn, fail, done
```

### 8. 출력은 핵심만 간결하게

불필요한 설명이나 사용법을 출력하지 않습니다.

```python
# ✅ 좋은 예
head("Install Serial Number")
desc("Install")
info(f"{IDENTITY_FILE}")

# ❌ 나쁜 예
desc("Install Serial Number")
info(f"Serial: {serial_number}")
info(f"Target: {IDENTITY_FILE}")
info("")
info("Usage in Python:")
info("  from nodi_edge.config import get_serial_number")
```

### 9. head과 desc 사용 규칙

- `head()`: 각 설치 파일의 **시작**에서 한 번만 호출 (파일 전체 카테고리)
- `desc()`: 내용이 **구분되는 위치**에 호출 (세부 단계)
- `desc()`는 **세밀하게 분리**: 각 작업 단위별로 구분

```python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Installation                    # 상위 섹션 (굵은 선)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

head("Install Serial Number")    # 파일 시작 (head 먼저)

# ────────────────────────────────────────────────────────────
# Check Prerequisites             # 하위 섹션 (얇은 선)
# ────────────────────────────────────────────────────────────

desc("Check Prerequisites")       # 전제조건 확인
if os.geteuid() != 0:
    ...

# ────────────────────────────────────────────────────────────
# Check Existing
# ────────────────────────────────────────────────────────────

desc("Check Existing")            # 기존 값 확인
if IDENTITY_FILE.exists():
    ...

# ────────────────────────────────────────────────────────────
# Create Directory
# ────────────────────────────────────────────────────────────

desc("Create Directory")          # 디렉토리 생성
IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
info(f"{IDENTITY_DIR}")

# ────────────────────────────────────────────────────────────
# Write Identity
# ────────────────────────────────────────────────────────────

desc("Write Identity")            # 파일 쓰기
IDENTITY_FILE.write_text(content)
info(f"{IDENTITY_FILE}")

# ────────────────────────────────────────────────────────────
# Set Hostname
# ────────────────────────────────────────────────────────────

desc("Set Hostname")              # 호스트명 설정
subprocess.run(["hostnamectl", "set-hostname", serial_number], check=True)
info(f"{serial_number}")

# ────────────────────────────────────────────────────────────
# Done
# ────────────────────────────────────────────────────────────

desc("Done")                      # 완료
info(f"serial_number={serial_number}")
```

## tool.py 출력 함수

| 함수 | 용도 | 스타일 |
|------|------|--------|
| `head(text)` | 파일 헤더 (굵은 박스) | ┏━━━┓ Cyan + Bold |
| `desc(text)` | 섹션 설명 (얇은 박스) | ┌───┐ Cyan |
| `info(text)` | 일반 정보 | 기본 |
| `warn(text)` | 경고 | Yellow |
| `fail(text)` | 실패/에러 | Red |
| `done(text)` | 완료/성공 | Green |

## 실행 예시

```bash
# 시리얼 번호 설치
sudo python3 /root/nodi-edge/install/install_serial.py NE-EBOW4

# 사용자 계정 설치
sudo python3 /root/nodi-edge/install/install_users.py
```
