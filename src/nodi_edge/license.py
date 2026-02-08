# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LicenseManager
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LicenseManager:

    def __init__(self,
                 pubkey_file: str,
                 cache_dir: str):
        self._pubkey_file = pubkey_file
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Load public key
        self._pubkey: Optional[Any] = None
        self._load_pubkey()

    def _load_pubkey(self) -> None:
        pubkey_path = Path(self._pubkey_file)
        if not pubkey_path.exists():
            return

        try:
            import jwt
            with open(pubkey_path, "r") as f:
                pem_data = f.read()
            # Store raw PEM for jwt.decode
            self._pubkey = pem_data
        except ImportError:
            raise ImportError("PyJWT is required for license validation: pip install PyJWT[crypto]")
        except Exception:
            self._pubkey = None


    # Validation
    # ──────────────────────────────────────────────────────────────────────

    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not self._pubkey:
            return None

        try:
            import jwt
            claims = jwt.decode(token, self._pubkey,
                                algorithms=["RS256"],
                                options={"require": ["exp", "app_id", "serial_number"]})
            return claims
        except Exception:
            return None

    def is_token_expired(self, token: str) -> bool:
        try:
            import jwt
            jwt.decode(token, self._pubkey,
                       algorithms=["RS256"],
                       options={"verify_exp": True})
            return False
        except Exception:
            return True


    # Token Cache (persistent, for offline operation)
    # ──────────────────────────────────────────────────────────────────────

    def cache_token(self, app_id: str, token: str) -> None:
        token_path = self._cache_dir / f"{app_id}.token"
        token_path.write_text(token, encoding="utf-8")

    def remove_cached_token(self, app_id: str) -> None:
        token_path = self._cache_dir / f"{app_id}.token"
        if token_path.exists():
            token_path.unlink()

    def load_cached_token(self, app_id: str) -> Optional[str]:
        token_path = self._cache_dir / f"{app_id}.token"
        if token_path.exists():
            return token_path.read_text(encoding="utf-8").strip()
        return None

    def load_cached_tokens(self) -> Dict[str, str]:
        tokens = {}
        for token_path in self._cache_dir.glob("*.token"):
            app_id = token_path.stem
            tokens[app_id] = token_path.read_text(encoding="utf-8").strip()
        return tokens
