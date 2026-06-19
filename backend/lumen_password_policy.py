"""
LUMEN IR0.6 — Password Policy
================================

A single source of truth for what counts as an acceptable password across
both staff (admin / operator) and investor authentication flows.

Policy (fixed in IR0.6):
  • length ≥ 8
  • at least 1 lowercase letter   [a-z]
  • at least 1 uppercase letter   [A-Z]
  • at least 1 digit              [0-9]
  • at least 1 special character  from a generous symbol set
  • no spaces / tabs / newlines
  • not on the common-password block-list

The module is pure (no HTTP, no DB) so it can be reused by any caller — the
staff registration endpoint, the investor sign-up endpoint, the password
reset flow, and the FE live strength meter (via ``policy_descriptor()``).

Public surface
--------------
* ``check_password(pw)``       -> PolicyCheck (ok / failures / per-rule map)
* ``policy_descriptor()``      -> JSON snapshot for the FE meter
* ``register_password_policy_routes(api_router)`` — mounts
    GET  /api/auth/password-policy   (public)
    POST /api/auth/password-policy/check  (public; takes the password,
                                          returns score only, never echoes)
* ``PasswordPolicyError``      — HTTPException subclass (400) used by callers
  that want to throw directly.

Both /api/auth/password-policy paths are already on the Access-Gate public
allowlist (IR0.1) — they must be reachable from the sign-up page before any
session exists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List

from fastapi import HTTPException

# ---- constants -----------------------------------------------------------
MIN_LENGTH = 8
MAX_LENGTH = 128                        # paranoia ceiling
SPECIALS = "!@#$%^&*()_+-=[]{};:,.?/\\|<>~'\""
_SPECIALS_SET = set(SPECIALS)

_RE_HAS_SPACE = re.compile(r"\s")
_RE_LOWER = re.compile(r"[a-z]")
_RE_UPPER = re.compile(r"[A-Z]")
_RE_DIGIT = re.compile(r"[0-9]")

# A small, deliberately public block-list — keeps the most obvious passwords
# out without pretending to be a full breach corpus (that belongs in zxcvbn /
# HIBP if/when we wire one in).
_COMMON = frozenset({
    "password", "password1", "password!", "Password1", "Password1!",
    "qwerty", "qwerty123", "12345678", "admin", "admin123", "administrator",
    "welcome", "welcome1", "letmein", "letmein1", "changeme", "changeme1",
    "iloveyou", "abc12345", "trustno1", "sunshine", "princess", "monkey",
    "dragon", "qazwsx", "football", "baseball",
    "lumen", "lumen123", "investor", "investor1",
})


@dataclass
class PolicyCheck:
    ok: bool
    failures: List[str]
    checks: Dict[str, bool]
    score: int                          # 0..100 (cheap, deterministic)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class PasswordPolicyError(HTTPException):
    def __init__(self, failures: List[str]):
        super().__init__(
            status_code=400,
            detail={
                "ok": False,
                "code": "password_policy_violation",
                "message": "Пароль не відповідає політиці безпеки.",
                "failures": failures,
            },
        )


def policy_descriptor() -> Dict[str, object]:
    """Public JSON snapshot of the rules — consumed by the FE meter."""
    return {
        "min_length": MIN_LENGTH,
        "max_length": MAX_LENGTH,
        "must_have_lower": True,
        "must_have_upper": True,
        "must_have_digit": True,
        "must_have_special": True,
        "no_whitespace": True,
        "specials": SPECIALS,
        "common_blocked": True,
    }


def _score_password(pw: str, checks: Dict[str, bool]) -> int:
    """Deterministic 0..100 score. Not a substitute for zxcvbn; gives the FE
    a stable visual hint without server-side complexity."""
    if not pw:
        return 0
    score = 0
    # length tiers
    if len(pw) >= 8:  score += 15
    if len(pw) >= 10: score += 10
    if len(pw) >= 12: score += 10
    if len(pw) >= 16: score += 10
    # character classes
    if checks.get("lower"):    score += 10
    if checks.get("upper"):    score += 10
    if checks.get("digit"):    score += 10
    if checks.get("special"):  score += 15
    if checks.get("no_whitespace"):  score += 5
    if checks.get("not_common"):     score += 5
    return min(100, score)


def check_password(pw: str) -> PolicyCheck:
    """Return a structured pass/fail check. ``ok=True`` iff every rule passes."""
    pw = pw or ""
    checks: Dict[str, bool] = {
        "length":         MIN_LENGTH <= len(pw) <= MAX_LENGTH,
        "lower":          bool(_RE_LOWER.search(pw)),
        "upper":          bool(_RE_UPPER.search(pw)),
        "digit":          bool(_RE_DIGIT.search(pw)),
        "special":        any(c in _SPECIALS_SET for c in pw),
        "no_whitespace":  not _RE_HAS_SPACE.search(pw),
        "not_common":     pw.lower() not in _COMMON,
    }
    failures: List[str] = [k for k, v in checks.items() if not v]
    ok = not failures
    return PolicyCheck(
        ok=ok,
        failures=failures,
        checks=checks,
        score=_score_password(pw, checks),
    )


# ---- HTTP surface --------------------------------------------------------
def register_password_policy_routes(api_router) -> None:
    """Mount the public descriptor + a check endpoint."""
    from fastapi import Body

    @api_router.get("/auth/password-policy")
    async def get_password_policy():
        return {"ok": True, "policy": policy_descriptor()}

    @api_router.post("/auth/password-policy/check")
    async def check_password_endpoint(payload: dict = Body(...)):
        pw = (payload or {}).get("password") or ""
        result = check_password(pw)
        # Never echo the password back; only the score + checks map.
        return {"ok": True, "result": result.to_dict()}


__all__ = [
    "check_password",
    "policy_descriptor",
    "PolicyCheck",
    "PasswordPolicyError",
    "register_password_policy_routes",
    "MIN_LENGTH",
    "MAX_LENGTH",
    "SPECIALS",
]
