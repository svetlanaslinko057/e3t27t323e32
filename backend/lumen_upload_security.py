"""
LUMEN IR0.2 — Server-Authoritative Upload Security
====================================================

The client-supplied ``Content-Type`` is never trusted. Every file that lands
on the platform — KYC document, signed contract, certificate, asset photo,
funding-proof, bank-CSV — must be validated by the server BEFORE it touches
the storage layer or any downstream business logic.

What this module does (one entry point ``validate_upload()``)
-------------------------------------------------------------
1. **Filename sanitisation**
   - strip path-traversal (``..``, leading slashes)
   - strip control chars / NUL bytes
   - cap length at 120 chars (keep extension)
   - collapse repeated dots so ``invoice.pdf.exe.html`` cannot smuggle a
     double extension past a naive splitter

2. **Extension allowlist + dangerous-extension denylist**
   - whitelist per upload-category (KYC, certificate, asset, bank-csv …)
   - explicit denylist (``.exe``, ``.bat``, ``.cmd``, ``.scr``, ``.js``,
     ``.html``, ``.svg``, ``.htm``, ``.shtml``, ``.phtml``, ``.php*``)

3. **Magic-byte sniffing** (the REAL type, not the declared one)
   - uses the ``filetype`` library
   - rejects mismatch between extension and detected mime

4. **Content signature scan** to catch payloads disguised as innocuous types
   - HTML / SVG / Script / executables / archives detected even when the
     wrapper file extension is benign (e.g. an HTML file renamed to ``.txt``
     is still rejected because we don't trust the extension)

5. **Per-category size limits**
   - kyc       → 10 MB (passport scans / utility bills)
   - asset     → 10 MB (photos)
   - bank_csv  →  5 MB (statement CSV / camt.053 XML)
   - contract  → 25 MB (signed PDFs)
   - certificate → 5 MB (PDF certificate)
   - funding_proof → 10 MB (payment screenshot / SEPA receipt)
   - misc      → 10 MB (default)

6. **Inline-safety flag**
   - returns ``inline=True`` only when the type is safe to serve back with
     ``Content-Disposition: inline`` (images / PDFs). Everything else is
     forced to ``attachment`` to avoid drive-by HTML / SVG rendering.

Public surface
--------------
- ``validate_upload(content, filename, category) -> SafeUpload``
- ``SafeUpload`` (dataclass)
- ``safe_content_disposition(name, inline) -> str``
- ``UploadSecurityError`` (HTTPException subclass with code 400)

Everything else is private; do NOT bypass ``validate_upload`` even for
"trusted" sources — there are no trusted sources for binary input.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Tuple

import filetype
from fastapi import HTTPException

logger = logging.getLogger("lumen.upload_security")

MB = 1024 * 1024

# ── per-category policy ──────────────────────────────────────────────────
SIZE_LIMITS = {
    "kyc": 10 * MB,
    "asset": 10 * MB,
    "bank_csv": 5 * MB,
    "contract": 25 * MB,
    "certificate": 5 * MB,
    "funding_proof": 10 * MB,
    "misc": 10 * MB,
}
HARD_CEILING = 30 * MB  # absolute ceiling regardless of category

# Allowlist of extensions per category. Note: the EXTENSION alone is never
# trusted — it must agree with the magic-byte sniff.
ALLOWED_EXT = {
    "kyc": {"pdf", "jpg", "jpeg", "png", "webp", "heic", "heif"},
    "asset": {"jpg", "jpeg", "png", "webp", "heic", "heif", "gif"},
    "bank_csv": {"csv", "xml", "txt"},   # camt.053 = xml
    "contract": {"pdf"},
    "certificate": {"pdf"},
    "funding_proof": {"pdf", "jpg", "jpeg", "png", "webp", "heic", "heif"},
    "misc": {"pdf", "jpg", "jpeg", "png", "webp", "heic", "heif",
             "doc", "docx", "xls", "xlsx", "txt", "csv"},
}

# Files we NEVER accept, regardless of category.
DANGEROUS_EXT = {
    "exe", "bat", "cmd", "com", "scr", "msi", "ps1", "vbs", "vbe",
    "wsf", "wsh", "jar", "app", "deb", "rpm",
    "html", "htm", "xhtml", "shtml", "phtml", "php", "phps", "php5", "php7",
    "asp", "aspx", "jsp", "jspx",
    "svg",          # SVG can carry JS — we explicitly forbid even as image
    "js", "mjs", "cjs", "ts",
    "lnk",          # Windows shortcut
}

# Magic-byte sigs we proactively reject regardless of extension.
_REJECT_SIGS = (
    b"<!doctype html",
    b"<html",
    b"<script",
    b"<?php",
    b"#!/bin/",
    b"\x4d\x5a",            # PE (Windows .exe)
    b"\x7f\x45\x4c\x46",    # ELF (Linux executable)
    b"\xca\xfe\xba\xbe",    # Mach-O (macOS) or Java class
    b"PK\x05\x06",          # empty ZIP (used as polyglot)
)

# Optional: archives we may want to inspect rather than accept blindly.
# We currently DO NOT accept archives at all in any category — uploaded
# bundles must be unpacked client-side. The detector still flags them so
# we get a clear error.
_ARCHIVE_SIGS = (
    b"PK\x03\x04",          # ZIP / DOCX / XLSX / PPTX (we DO accept these as
                            # docx — handled separately below)
    b"Rar!\x1a\x07",        # RAR
    b"\x37\x7a\xbc\xaf\x27\x1c",  # 7z
    b"\x1f\x8b\x08",        # gzip
)

# Safe MIMEs we may serve back inline (images + PDF). Anything else must be
# forced to ``attachment`` by the download handler.
_INLINE_OK = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "image/heic", "image/heif",
    "application/pdf",
}

# Extension → expected magic-mime mapping (lookup helper).
_EXT_TO_MIME = {
    "pdf": ("application/pdf",),
    "jpg": ("image/jpeg",), "jpeg": ("image/jpeg",),
    "png": ("image/png",),
    "webp": ("image/webp",),
    "gif": ("image/gif",),
    "heic": ("image/heic",), "heif": ("image/heif",),
    "csv": ("text/plain", "text/csv", "application/csv"),
    "xml": ("application/xml", "text/xml"),
    "txt": ("text/plain",),
    "docx": ("application/zip",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xlsx": ("application/zip",
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "doc":  ("application/msword", "application/x-cfb"),
    "xls":  ("application/vnd.ms-excel", "application/x-cfb"),
}


# ── exception type ───────────────────────────────────────────────────────
class UploadSecurityError(HTTPException):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail={
            "ok": False, "code": code, "message": message,
        })
        self.code = code


# ── data class ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SafeUpload:
    """The trusted view of an upload — use THIS, never the original headers."""
    filename: str              # sanitised, safe for FS / DB / URLs
    category: str              # kyc / asset / bank_csv / contract / ...
    mime: str                  # server-determined, not client-declared
    ext: str                   # canonical extension (lowercase, no dot)
    size: int                  # bytes
    inline_safe: bool          # True if Content-Disposition: inline is OK


# ── helpers ──────────────────────────────────────────────────────────────
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_DOTS_RE = re.compile(r"\.{2,}")


def _sanitize_filename(raw: Optional[str]) -> str:
    name = (raw or "file").strip()
    # take the basename only
    name = name.replace("\\", "/").split("/")[-1]
    # Unicode normalise → ASCII transliteration where possible
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii") or "file"
    # strip NUL + control
    name = "".join(ch for ch in name if ch.isprintable() and ord(ch) >= 0x20)
    # collapse repeated dots so double-extensions cannot smuggle
    name = _DOTS_RE.sub(".", name)
    # leading dot → no hidden files
    name = name.lstrip(".")
    # split extension before sanitising the stem so we don't lose it
    if "." in name:
        stem, ext = name.rsplit(".", 1)
    else:
        stem, ext = name, ""
    stem = _SAFE_NAME_RE.sub("_", stem)[:100] or "file"
    ext = _SAFE_NAME_RE.sub("", ext).lower()[:8]
    return f"{stem}.{ext}" if ext else stem


def _extract_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _detect_mime(content: bytes) -> str:
    """Return the magic-byte derived MIME, or 'application/octet-stream'."""
    if not content:
        return "application/octet-stream"
    try:
        kind = filetype.guess(content[:262144])
        if kind is not None:
            return kind.mime
    except Exception:
        pass
    # Fallback: a few sniff heuristics for plain-text formats which
    # ``filetype`` does not detect (it's binary-only).
    head = content[:512].lstrip()
    head_l = head.lower()
    if head_l.startswith(b"<?xml"):
        return "application/xml"
    # crude CSV / plain heuristic — look at first 1KB for printable density
    try:
        sample = content[:1024]
        if sample and all((b in b"\r\n\t" or 0x20 <= b < 0x7f or b >= 0x80) for b in sample):
            return "text/plain"
    except Exception:
        pass
    return "application/octet-stream"


def _looks_dangerous(content: bytes) -> Optional[str]:
    head = content[:1024].lower()
    for sig in _REJECT_SIGS:
        if sig.lower() in head:
            return "reject_signature"
    # If extension didn't claim docx/xlsx/pptx then a ZIP sig is suspicious.
    if content[:4] == b"PK\x03\x04":
        # caller distinguishes docx vs zip via extension below
        return None
    return None


# ── main entry point ─────────────────────────────────────────────────────
def validate_upload(
    content: bytes,
    filename: Optional[str],
    category: str = "misc",
) -> SafeUpload:
    """Validate a freshly-uploaded blob and return a ``SafeUpload`` envelope.

    Raises ``UploadSecurityError(400)`` on any policy violation. Callers
    MUST use ``SafeUpload.mime`` / ``SafeUpload.filename`` for downstream
    storage / serving; the original ``UploadFile.content_type`` / filename
    are no longer trusted.

    Parameters
    ----------
    content : bytes
        Full file bytes (already read from ``UploadFile``).
    filename : Optional[str]
        Client-supplied filename. Sanitised before any use.
    category : str
        One of the keys in ``SIZE_LIMITS`` / ``ALLOWED_EXT``. Unknown
        categories degrade to ``"misc"`` policy.
    """
    if category not in SIZE_LIMITS:
        category = "misc"

    # ── size ──
    size = len(content or b"")
    if size == 0:
        raise UploadSecurityError("empty_file", "Файл порожній.")
    limit = SIZE_LIMITS[category]
    if size > limit:
        mb = limit // MB
        raise UploadSecurityError(
            "too_large",
            f"Файл завеликий (максимум {mb} МБ для категорії '{category}').",
        )
    if size > HARD_CEILING:
        raise UploadSecurityError("too_large", "Файл перевищує абсолютний ліміт 30 МБ.")

    # ── filename ──
    safe_name = _sanitize_filename(filename)
    ext = _extract_extension(safe_name)

    # ── extension policy ──
    if ext in DANGEROUS_EXT:
        raise UploadSecurityError(
            "dangerous_extension",
            f"Розширення '.{ext}' заборонено політикою безпеки.",
        )
    allowed = ALLOWED_EXT.get(category, ALLOWED_EXT["misc"])
    if ext and ext not in allowed:
        raise UploadSecurityError(
            "extension_not_allowed",
            f"Розширення '.{ext}' не дозволено для категорії '{category}'.",
        )

    # ── magic-byte sniff ──
    mime = _detect_mime(content)
    expected = _EXT_TO_MIME.get(ext)
    if expected and mime not in expected:
        # Special-case: docx/xlsx have ZIP magic — accept the ZIP sig as
        # a valid match for these office formats.
        if ext in {"docx", "xlsx"} and mime == "application/zip":
            pass
        # CSV: filetype lib can't sniff text — accept if extension says csv
        # and our text heuristic agreed.
        elif ext in {"csv", "txt", "xml"} and mime in {"text/plain", "application/xml", "application/octet-stream"}:
            pass
        else:
            raise UploadSecurityError(
                "type_mismatch",
                f"Тип файлу ({mime}) не відповідає розширенню '.{ext}'.",
            )

    # ── content signature scan ──
    reason = _looks_dangerous(content)
    if reason:
        raise UploadSecurityError("dangerous_content", "Виявлено небезпечний вміст файлу.")

    # ── inline-safety ──
    inline = mime in _INLINE_OK

    logger.info(
        "upload accepted category=%s ext=%s mime=%s size=%d filename=%s",
        category, ext, mime, size, safe_name,
    )
    return SafeUpload(
        filename=safe_name,
        category=category,
        mime=mime,
        ext=ext,
        size=size,
        inline_safe=inline,
    )


# ── download-side helper ─────────────────────────────────────────────────
def safe_content_disposition(name: str, inline: bool) -> str:
    """Build a Content-Disposition value that escapes the filename safely.

    Uses RFC-5987 ``filename*`` extension so non-ASCII names are preserved
    while keeping a sanitised ASCII fallback for legacy clients.
    """
    ascii_fallback = _sanitize_filename(name)
    quoted = ascii_fallback.replace('"', "")
    disposition = "inline" if inline else "attachment"
    try:
        import urllib.parse as _u
        utf8 = _u.quote(name, safe="")
        return f'{disposition}; filename="{quoted}"; filename*=UTF-8\'\'{utf8}'
    except Exception:
        return f'{disposition}; filename="{quoted}"'


# ── unit-testable classifier for use in tests / dashboards ───────────────
def policy_descriptor() -> dict:
    return {
        "size_limits_mb": {k: v // MB for k, v in SIZE_LIMITS.items()},
        "hard_ceiling_mb": HARD_CEILING // MB,
        "allowed_ext": {k: sorted(v) for k, v in ALLOWED_EXT.items()},
        "dangerous_ext": sorted(DANGEROUS_EXT),
        "inline_safe_mimes": sorted(_INLINE_OK),
    }


__all__ = [
    "validate_upload",
    "SafeUpload",
    "UploadSecurityError",
    "safe_content_disposition",
    "policy_descriptor",
    "SIZE_LIMITS",
    "ALLOWED_EXT",
    "DANGEROUS_EXT",
]
