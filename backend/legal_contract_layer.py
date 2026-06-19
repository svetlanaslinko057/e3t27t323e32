"""
Legal Contract Signing — Phase 1 (core backend).

Scope (per product spec, Phase 1):
  1. Legal profile collected ONLY when user signs their first contract.
  2. Contract becomes an immutable snapshot at the moment of signing:
       - contract_version
       - html_snapshot
       - project_snapshot
       - legal_profile_snapshot
       - sha256_hash
       - signed_at / ip / user_agent / otp_verified
  3. Click-wrap + email OTP (reuses existing auth_otp email pipeline,
     mocked via Resend in dev — code shows up in backend.err.log).
  4. Full audit trail in `contract_signatures`.
  5. Contract-status gate:
       estimate_approved → agreement_required → legal_profile_completed
       → otp_verified_signature → agreement_signed → payment_unlocked
       → project_starts_after_payment

Phase 2 (NOT here): PDF generation (with HTML fallback), mobile+web
signing UI, Documents screen, payment gate wiring, production template.

Models / Collections
--------------------
client_legal_profiles : { user_id, full_name, tax_id, registered_address,
                          country, phone, created_at, updated_at }
contract_templates    : { version, status, body_html, created_at } — the
                        versioned English placeholder. Marked
                        `placeholder_pending_legal_review`.
contracts             : { contract_id, user_id, project_id, estimate_id?,
                          state, template_version, price, payment_plan,
                          modules, timeline, created_at,
                          signed_at?, html_snapshot?, project_snapshot?,
                          legal_profile_snapshot?, sha256_hash?,
                          pdf_status, pdf_bytes? (base64) }
contract_signatures   : per-sign audit record (immutable).
contract_otp_codes    : { contract_id, user_id, code_hash, expires_at,
                          attempts, consumed_at? } — short-lived.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("legal_contract")

# ---------------------------------------------------------------------------
# Wiring — set by init_router() from server.py
# ---------------------------------------------------------------------------

_db = None
_get_current_user = None
_send_otp_email = None  # async (email, code, ttl_minutes) -> msg_id | None
_email_is_configured = None  # () -> bool

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TEMPLATE_VERSION = "v1.0-placeholder"
TEMPLATE_STATUS = "placeholder_pending_legal_review"

OTP_TTL_SECONDS = 10 * 60
OTP_RESEND_COOLDOWN_SECONDS = 30
OTP_MAX_ATTEMPTS = 5

# DEV: if Resend not configured, surface OTP code in response so client
# can sign without a real inbox. Same pattern as auth_otp.
def _dev_mode() -> bool:
    try:
        return not bool(_email_is_configured and _email_is_configured())
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _client_ip(request: Request) -> str:
    # Respect proxy header when present (kubernetes ingress).
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return (request.client.host if request.client else "") or ""


def _client_ua(request: Request) -> str:
    return request.headers.get("user-agent", "") or ""


# ---------------------------------------------------------------------------
# Contract template (English placeholder — Phase 1)
# ---------------------------------------------------------------------------


DEFAULT_TEMPLATE_HTML = """
<section class="contract">
<h1>Software Development &amp; Delivery Agreement</h1>
<p class="meta">Template version: {template_version} — {template_status}</p>
<p class="meta">Effective date: at the moment of electronic acceptance by the Client.</p>

<h2>1. Parties</h2>
<p>
  This Software Development &amp; Delivery Agreement (the
  &ldquo;<b>Agreement</b>&rdquo;) is made between:
</p>
<ul>
  <li>
    <b>Client</b> — <b>{client_name}</b>{client_tax_block}, having its
    billing address at <b>{client_address}</b>, contactable by phone
    <b>{client_phone}</b> and by email <b>{client_email}</b>;
  </li>
  <li>
    <b>Provider</b> — <b>{provider_party}</b>, operating the EVA-X /
    ATLAS DevOS product delivery system, having registered address at
    <b>{provider_address}</b>{provider_tax_block}.
  </li>
</ul>
<p>
  The Client and the Provider are each a &ldquo;Party&rdquo; and
  together the &ldquo;Parties&rdquo;.
</p>

<h2>2. Project description</h2>
<p>
  The Provider will deliver the project titled
  <b>&ldquo;{project_title}&rdquo;</b>, an integrated software product
  as described in the project brief and scope snapshot bound to this
  Agreement as an immutable evidence item (Section 18).
</p>

<h2>3. Scope of work</h2>
<p>
  The scope consists of the following modules, which together form a
  single, indivisible deliverable:
</p>
{modules_html}
<p>
  Anything not explicitly named in this scope, in the bound estimate,
  or in the bound milestones list is out of scope and is governed by
  Section 8 (Change requests).
</p>

<h2>4. Deliverables</h2>
<p>
  For each module the Provider delivers (a) the working software
  artefact, (b) the source code, configuration and build manifests,
  (c) a short delivery note describing what was implemented and how to
  verify it, and (d) a passing human-validation gate (Section 7).
</p>

<h2>5. Timeline and milestones</h2>
<p>
  Estimated overall timeline: <b>{timeline}</b>. The timeline starts
  from the moment the initial payment named in Section 6 is received.
  Material timeline impact from Client-side blockers (missing inputs,
  delayed feedback, change requests) extends the timeline by the
  equivalent amount, recorded transparently in the workspace.
</p>

<h2>6. Price and payment terms</h2>
<p>Total project price: <b>{price}</b>.</p>
{payment_plan_html}
<p>
  Payments are made via the payment method selected by the Client and
  recorded as <b>{payment_method}</b>. Invoices are issued for each
  payment trigger and are payable within seven (7) days of issue
  unless an alternative cadence is stated in the payment schedule.
</p>

<h2>7. Human validation, QA and acceptance</h2>
<p>
  Each delivered module is examined by an independent human validator
  using the Provider&rsquo;s Reality / HVL validation layer
  (<b>{hvl_summary}</b>). The Client then has an acceptance window
  during which they can request fixes or sign-off in the workspace.
  If no response is recorded within the acceptance window, the module
  is treated as accepted.
</p>

<h2>8. Change requests</h2>
<p>
  Any change to scope, deliverables, timeline or price occurs by
  written change request inside the workspace. Each change request is
  priced and scheduled separately and only enters work after the
  Client&rsquo;s written approval.
</p>

<h2>9. Client obligations</h2>
<p>
  The Client agrees to (a) provide accurate brief and feedback in a
  timely manner; (b) appoint a single primary decision-maker for the
  duration of the project; (c) provide any third-party credentials,
  brand assets, and external system access reasonably necessary to
  deliver the modules in scope; and (d) make payments on the agreed
  schedule.
</p>

<h2>10. Provider obligations</h2>
<p>
  The Provider agrees to (a) deliver the modules in scope using
  qualified engineers and Provider&rsquo;s human validation layer; (b)
  surface risk, blockers and timeline impact transparently in the
  workspace; (c) keep the Client&rsquo;s materials confidential under
  Section 14; and (d) preserve immutable evidence of every signing,
  payment and acceptance event for at least the retention period in
  Section 18.
</p>

<h2>11. Developer / operator subcontracting</h2>
<p>
  The Client acknowledges that work is performed by a curated pool of
  developers and operators sourced and supervised by the Provider. The
  Provider remains contractually responsible to the Client for the
  delivery in full and for all sub-tier engagements. Names of the
  assigned developers and operators are visible to the Client inside
  the workspace.
</p>

<h2>12. Intellectual property</h2>
<p>
  Upon full payment of the price in Section 6, all project-specific
  deliverables created under this Agreement (source code, design
  assets, configuration, project documentation) transfer to the
  Client. Pre-existing components of the Provider&rsquo;s platform
  (the platform code itself, internal libraries, internal models,
  validation pipelines) remain the property of the Provider and are
  licensed to the Client on a perpetual, royalty-free, non-exclusive
  basis solely to operate the delivered product.
</p>

<h2>13. Confidentiality</h2>
<p>
  Each Party shall keep the other Party&rsquo;s non-public
  information confidential, use it only for the purpose of performing
  this Agreement, and protect it with at least the same degree of care
  it applies to its own confidential information. This obligation
  survives termination for three (3) years.
</p>

<h2>14. Limitation of liability</h2>
<p>
  To the maximum extent permitted by applicable law, each
  Party&rsquo;s aggregate liability arising out of or in connection
  with this Agreement is limited to the total amount actually paid by
  the Client under this Agreement during the twelve (12) months
  preceding the event giving rise to the claim. Neither Party is
  liable for indirect, incidental, consequential, special or punitive
  damages, including lost profits or loss of goodwill.
</p>

<h2>15. Refund and cancellation</h2>
<p>
  Either Party may terminate this Agreement in writing. Work completed
  up to the termination date, including modules in flight, is invoiced
  at actual cost and is due on termination. Unused portions of pre-paid
  milestones are refunded within thirty (30) days. Once a module is
  accepted under Section 7, its payment is non-refundable.
</p>

<h2>16. Dispute resolution</h2>
<p>
  The Parties shall first attempt to resolve any dispute in good
  faith through direct discussion. If a dispute is not resolved within
  thirty (30) days of written notice, the Parties shall attempt
  resolution by mediation. Either Party may thereafter pursue any
  remedy available at law.
</p>

<h2>17. Governing law</h2>
<p>
  This Agreement is governed by, and construed in accordance with,
  the laws of the Provider&rsquo;s jurisdiction of incorporation,
  without regard to its conflict-of-laws principles. The Parties
  submit to the exclusive jurisdiction of the competent courts of
  that jurisdiction for any matter not resolved under Section 16.
  <span class="placeholder">[Final jurisdiction text is set by the
  Provider&rsquo;s legal team and locked in the platform legal entity
  snapshot bound to this Agreement.]</span>
</p>

<h2>18. Electronic signature and evidence package</h2>
<p>
  This Agreement is signed electronically in accordance with applicable
  electronic-signature laws (signature level: <b>{signature_level}</b>).
  The Client confirms identity by completing the click-wrap acceptance
  flow and by entering a one-time code delivered to the registered
  email address. The Provider counter-signs at the same moment using a
  deterministic platform signing identity. The following items are
  captured at the moment of signing and stored as immutable evidence
  of mutual acceptance:
</p>
<ul>
  <li>Full HTML snapshot of this Agreement</li>
  <li>Snapshot of the Client&rsquo;s legal profile</li>
  <li>Snapshot of the project brief, scope, modules, milestones, price and payment plan</li>
  <li>Snapshot of the accepted estimate and selected payment method</li>
  <li>Snapshot of the Provider&rsquo;s legal entity at the moment of signing</li>
  <li>SHA-256 hash of the combined snapshot</li>
  <li>Signing timestamp, IP address, user-agent string</li>
  <li>Confirmation of the one-time code used to verify identity</li>
  <li>Template version, acceptance-copy version, signature level</li>
</ul>

<h2>Acknowledgements</h2>
<ul>
  <li>I confirm my legal details are correct.</li>
  <li>I agree to the project scope, payment schedule and terms.</li>
  <li>I understand development starts after initial payment.</li>
</ul>
</section>
""".strip()


def _render_template(
    *,
    client_name: str,
    client_tax_id: str,
    client_address: str,
    project_title: str,
    modules: List[Dict[str, Any]],
    timeline: str,
    price: str,
    payment_plan: List[Dict[str, Any]],
    # CONTRACT-P4 / P5 — extended composition fields. All optional so
    # existing call sites keep working; missing fields fall back to
    # human-readable placeholders that legal review can pick up.
    client_phone: Optional[str] = None,
    client_email: Optional[str] = None,
    payment_method: Optional[str] = None,
    hvl_summary: Optional[str] = None,
    provider_party: Optional[str] = None,
    provider_address: Optional[str] = None,
    provider_tax_id: Optional[str] = None,
    signature_level: Optional[str] = None,
) -> str:
    modules_html = "<ul>" + "".join(
        f"<li><b>{(m.get('title') or m.get('name') or '').strip()}</b>"
        f"{' — ' + m.get('description') if m.get('description') else ''}</li>"
        for m in (modules or [])
    ) + "</ul>"
    if not modules:
        modules_html = "<p class='placeholder'>[Scope modules attached as snapshot]</p>"

    if payment_plan:
        payment_plan_html = "<ol>" + "".join(
            f"<li><b>{(p.get('label') or p.get('name') or 'Milestone').strip()}</b>: "
            f"{p.get('amount', '')} — {p.get('trigger', 'on agreed milestone')}</li>"
            for p in payment_plan
        ) + "</ol>"
    else:
        payment_plan_html = (
            "<p class='placeholder'>[Payment plan attached as snapshot]</p>"
        )

    # Tax block — appears only if a tax_id is set (Client may be an
    # individual with no tax_id by default per the data-minimization rule).
    client_tax_block = (
        f", identified by tax ID <b>{client_tax_id}</b>"
        if client_tax_id and client_tax_id != "[Tax ID]"
        else ""
    )
    provider_tax_block = (
        f", identified by tax ID <b>{provider_tax_id}</b>"
        if provider_tax_id and not provider_tax_id.startswith("[")
        else ""
    )

    return DEFAULT_TEMPLATE_HTML.format(
        template_version=TEMPLATE_VERSION,
        template_status=TEMPLATE_STATUS,
        client_name=client_name or "[Client]",
        client_tax_block=client_tax_block,
        client_address=client_address or "[Billing address]",
        client_phone=client_phone or "[Phone]",
        client_email=client_email or "[Email]",
        project_title=project_title or "[Project]",
        modules_html=modules_html,
        timeline=timeline or "[Timeline]",
        price=price or "[Price]",
        payment_plan_html=payment_plan_html,
        payment_method=payment_method or "the payment method selected at signing",
        hvl_summary=hvl_summary or "automated and human review across acceptance criteria",
        provider_party=provider_party or "EVA-X / ATLAS DevOS",
        provider_address=provider_address or "EVA-X Platform — Operational HQ",
        provider_tax_block=provider_tax_block,
        signature_level=signature_level or "simple electronic signature (SES)",
    )


# ---------------------------------------------------------------------------
# Pydantic request/response models (CONTRACT-P3 — data-minimization model)
# ---------------------------------------------------------------------------
#
# Design principles (locked):
#   • Default required set = identity + billing reachability only.
#     name + email (from session) + phone + billing address + country.
#   • tax_id is OPTIONAL by default. Required only if the user is a
#     company OR jurisdiction needs it on the invoice.
#   • passport / ID photo / personal IDs are NEVER collected by default.
#     Enhanced KYC happens later, via an external provider, only for
#     high-value contracts or flagged risk.
#   • legal_type splits the contract party shape (Section 1 of template).


class LegalProfileIn(BaseModel):
    # --- Always required ---
    legal_type: str = Field(..., pattern=r"^(individual|company)$")
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    middle_name: Optional[str] = Field(default=None, max_length=80)
    phone: str = Field(..., min_length=4, max_length=40)
    billing_address: str = Field(..., min_length=3, max_length=300)
    country: str = Field(..., min_length=2, max_length=64)
    city: str = Field(..., min_length=1, max_length=80)
    postal_code: str = Field(..., min_length=1, max_length=20)

    # --- Required when legal_type=company (validated in _upsert_legal_profile) ---
    company_name: Optional[str] = Field(default=None, max_length=200)
    company_registration_number: Optional[str] = Field(default=None, max_length=64)

    # --- Optional for both ---
    tax_id: Optional[str] = Field(default=None, max_length=32)

    # --- Convenience for legacy callers (one-line full_name) ---
    # If provided we use it; otherwise we synthesise from first/last/middle.
    full_name: Optional[str] = Field(default=None, max_length=200)


class PrepareContractIn(BaseModel):
    project_id: Optional[str] = None
    estimate_id: Optional[str] = None
    # For dev/demo — caller can pass inline fields when we don't have
    # a persisted project doc to pull from yet.
    project_title: Optional[str] = None
    price: Optional[str] = None
    timeline: Optional[str] = None
    modules: Optional[List[Dict[str, Any]]] = None
    payment_plan: Optional[List[Dict[str, Any]]] = None


class SignRequestIn(BaseModel):
    # The client may re-submit / update legal data right before signing.
    legal_profile: LegalProfileIn


class SignConfirmIn(BaseModel):
    legal_profile: LegalProfileIn
    acknowledgements: Dict[str, bool] = Field(default_factory=dict)
    # Required keys: legal_details_correct, scope_terms_agreed,
    # start_after_payment_understood
    otp_code: str = Field(..., min_length=4, max_length=10)
    terms_version: str = Field(default="v1.0")


# ---------------------------------------------------------------------------
# CONTRACT-P7 — Data protection helpers
# ---------------------------------------------------------------------------
#
# Sensitive fields (tax_id, company_registration_number) are encrypted
# at rest using AES-128-CBC-style symmetric encryption via cryptography's
# Fernet (HMAC-SHA256 authenticated). The encryption key is derived from
# `LEGAL_DATA_ENCRYPTION_KEY` env. If missing, a dev-only deterministic
# key is generated (logged at boot) so the flow works in preview; for
# production this MUST be set to a 32-byte url-safe base64 key.


_FERNET = None  # lazy cache


def _get_fernet():
    """Return a Fernet instance from env or dev-derived key.

    NEVER use the dev path in production. If the env var is missing in
    a real deploy, set LEGAL_DATA_ENCRYPTION_KEY to a real key via:
        python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    try:
        from cryptography.fernet import Fernet
    except Exception:  # noqa: BLE001 — cryptography is in requirements.txt
        return None
    key = os.getenv("LEGAL_DATA_ENCRYPTION_KEY") or ""
    if not key:
        # DEV fallback — derive from a stable salt; logs a warning ONCE.
        import base64 as _b64
        derived = hashlib.sha256(
            (os.getenv("MONGO_URL", "dev") + "::legal_profile_v1").encode()
        ).digest()
        key = _b64.urlsafe_b64encode(derived).decode()
        logger.warning(
            "LEGAL_DATA_ENCRYPTION_KEY not set — using dev-derived key. "
            "For production set this env to a 32-byte url-safe base64 key."
        )
    try:
        _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Fernet init failed ({e}); sensitive fields stored as plaintext.")
        _FERNET = None
    return _FERNET


def _enc(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    f = _get_fernet()
    if not f:
        return value  # graceful — never block the flow
    try:
        return "fernet::" + f.encrypt(value.encode("utf-8")).decode("ascii")
    except Exception:  # noqa: BLE001
        return value


def _dec(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    if not token.startswith("fernet::"):
        return token  # legacy plaintext
    f = _get_fernet()
    if not f:
        return None
    try:
        return f.decrypt(token[len("fernet::"):].encode("ascii")).decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def _profile_public(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return a profile dict with sensitive fields decrypted for the
    OWNER. Admin / audit access should use `_profile_admin_view` which
    is logged."""
    if not doc:
        return doc
    out = dict(doc)
    out["tax_id"] = _dec(doc.get("tax_id_enc")) if doc.get("tax_id_enc") else doc.get("tax_id")
    out["company_registration_number"] = (
        _dec(doc.get("company_registration_number_enc"))
        if doc.get("company_registration_number_enc")
        else doc.get("company_registration_number")
    )
    # never leak the encrypted blob to UI
    out.pop("tax_id_enc", None)
    out.pop("company_registration_number_enc", None)
    return out


async def _audit_legal_access(
    *,
    actor_user_id: str,
    actor_role: str,
    subject_user_id: str,
    reason: str,
    request_id: Optional[str] = None,
) -> None:
    """Append-only admin access log for legal profile reads.

    Anyone reading another user's legal profile (admin, support, audit
    bot) leaves a row here. Owner reading their own profile is NOT
    logged (it's their own data — logging it adds noise without value).
    """
    if actor_user_id == subject_user_id:
        return
    try:
        await _db.legal_access_audit.insert_one({
            "audit_id": f"laa_{uuid.uuid4().hex[:12]}",
            "actor_user_id": actor_user_id,
            "actor_role": actor_role,
            "subject_user_id": subject_user_id,
            "reason": reason,
            "request_id": request_id,
            "at": _now_iso(),
        })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"legal access audit log failed: {e}")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _get_or_null_legal_profile(user_id: str) -> Optional[Dict[str, Any]]:
    doc = await _db.client_legal_profiles.find_one({"user_id": user_id}, {"_id": 0})
    return _profile_public(doc) if doc else None


async def _upsert_legal_profile(user_id: str, p: LegalProfileIn) -> Dict[str, Any]:
    """Upsert with data-minimization + encryption for sensitive fields.

    Enforces the company branch: if legal_type=company, company_name +
    company_registration_number are required.
    """
    if p.legal_type == "company":
        if not (p.company_name and p.company_name.strip()):
            raise HTTPException(status_code=422, detail="company_name is required when legal_type=company")
        if not (p.company_registration_number and p.company_registration_number.strip()):
            raise HTTPException(status_code=422, detail="company_registration_number is required when legal_type=company")

    now = _now_iso()
    existing = await _db.client_legal_profiles.find_one({"user_id": user_id}, {"_id": 0})

    # Synthesise full_name if caller didn't supply one.
    full_name = (p.full_name or "").strip()
    if not full_name:
        parts = [p.first_name.strip(), (p.middle_name or "").strip(), p.last_name.strip()]
        full_name = " ".join(x for x in parts if x)

    doc = {
        "user_id": user_id,
        "legal_type": p.legal_type,
        "full_name": full_name,
        "first_name": p.first_name.strip(),
        "last_name": p.last_name.strip(),
        "middle_name": (p.middle_name or "").strip() or None,
        "phone": p.phone.strip(),
        "billing_address": p.billing_address.strip(),
        # legacy alias for snapshots / template rendering
        "registered_address": p.billing_address.strip(),
        "country": p.country.strip(),
        "city": p.city.strip(),
        "postal_code": p.postal_code.strip(),
        "company_name": (p.company_name or "").strip() or None,
        # Sensitive fields — encrypted at rest
        "tax_id_enc": _enc((p.tax_id or "").strip() or None),
        "company_registration_number_enc": _enc(
            (p.company_registration_number or "").strip() or None
        ),
        # Cleared plaintext shadows from legacy rows
        "tax_id": None,
        "company_registration_number": None,
        # Verification level — default basic; enhanced/external_kyc set later
        "verification_level": (existing or {}).get("verification_level", "basic"),
        "updated_at": now,
        "completed_at": (existing or {}).get("completed_at", now),
        "created_at": existing["created_at"] if existing else now,
    }
    await _db.client_legal_profiles.update_one(
        {"user_id": user_id},
        {"$set": doc},
        upsert=True,
    )
    return _profile_public(doc)


def _contract_state_public(c: Dict[str, Any]) -> Dict[str, Any]:
    """Strip heavy / secret fields for list views."""
    return {
        "contract_id": c["contract_id"],
        "user_id": c["user_id"],
        "project_id": c.get("project_id"),
        "estimate_id": c.get("estimate_id"),
        "state": c["state"],
        "template_version": c["template_version"],
        "template_status": c.get("template_status"),
        "price": c.get("price"),
        "timeline": c.get("timeline"),
        "project_title": c.get("project_title"),
        "created_at": c["created_at"],
        "signed_at": c.get("signed_at"),
        "sha256_hash": c.get("sha256_hash"),
        "pdf_status": c.get("pdf_status", "not_generated"),
    }


async def _build_project_snapshot(
    user_id: str,
    body: PrepareContractIn,
) -> Dict[str, Any]:
    """Pull project/estimate data if we have it; otherwise fall back to
    whatever the caller passed inline. This keeps Phase 1 usable even
    before estimate layer is wired."""
    snapshot: Dict[str, Any] = {
        "project_id": body.project_id,
        "estimate_id": body.estimate_id,
        "project_title": body.project_title or "[Project]",
        "price": body.price or "[Price]",
        "timeline": body.timeline or "[Timeline]",
        "modules": body.modules or [],
        "payment_plan": body.payment_plan or [],
    }

    # If we have a project_id, try to load real data.
    if body.project_id:
        try:
            proj = await _db.projects.find_one(
                {"$or": [{"project_id": body.project_id}, {"id": body.project_id}]},
                {"_id": 0},
            )
            if proj:
                snapshot["project_title"] = (
                    proj.get("title") or proj.get("name") or snapshot["project_title"]
                )
                snapshot["price"] = (
                    proj.get("price")
                    or proj.get("total_cost")
                    or snapshot["price"]
                )
                snapshot["timeline"] = (
                    proj.get("timeline")
                    or proj.get("deadline")
                    or snapshot["timeline"]
                )
                if not snapshot["modules"]:
                    try:
                        mods = await _db.modules.find(
                            {"project_id": body.project_id}, {"_id": 0}
                        ).to_list(length=200)
                        snapshot["modules"] = mods or []
                    except Exception:  # noqa: BLE001
                        pass
                snapshot["_project_loaded"] = True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"contract snapshot: project load failed: {e}")

    return snapshot


# ---------------------------------------------------------------------------
# OTP (contract-specific, independent from auth_otp)
# ---------------------------------------------------------------------------


def _gen_code() -> str:
    return f"{random.SystemRandom().randint(0, 999_999):06d}"


def _code_hash(code: str, contract_id: str) -> str:
    # Namespaced HMAC so a leaked auth_otp hash can't be replayed here.
    key = os.environ.get("CONTRACT_OTP_SECRET", "atlas-contract-otp-dev-secret").encode()
    return hmac.new(key, f"{contract_id}:{code}".encode(), hashlib.sha256).hexdigest()


async def _issue_contract_otp(contract_id: str, user_id: str, email: str) -> Dict[str, Any]:
    now = _now()
    # Cooldown
    latest = await _db.contract_otp_codes.find_one(
        {"contract_id": contract_id, "user_id": user_id, "consumed_at": None},
        sort=[("created_at", -1)],
    )
    if latest:
        try:
            created = datetime.fromisoformat(latest["created_at"])
        except Exception:  # noqa: BLE001
            created = now
        age = (now - created).total_seconds()
        if age < OTP_RESEND_COOLDOWN_SECONDS:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {int(OTP_RESEND_COOLDOWN_SECONDS - age)}s before requesting a new code.",
            )

    code = _gen_code()
    doc = {
        "otp_id": f"cotp_{uuid.uuid4().hex[:12]}",
        "contract_id": contract_id,
        "user_id": user_id,
        "email": email,
        "code_hash": _code_hash(code, contract_id),
        "attempts": 0,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=OTP_TTL_SECONDS)).isoformat(),
        "consumed_at": None,
    }
    await _db.contract_otp_codes.insert_one(doc)

    # Deliver. Fall back to DEV surfacing when Resend not configured.
    delivered = False
    msg_id: Optional[str] = None
    dev_mode = _dev_mode()
    if not dev_mode and _send_otp_email:
        try:
            msg_id = await _send_otp_email(email, code, ttl_minutes=OTP_TTL_SECONDS // 60)
            delivered = True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"contract OTP email failed, falling back to dev: {e}")
            dev_mode = True

    result = {
        "otp_id": doc["otp_id"],
        "expires_at": doc["expires_at"],
        "channel": "email",
        "dev_mode": dev_mode,
        "delivered": delivered,
        "message_id": msg_id,
    }
    if dev_mode:
        # Same pattern as auth_otp — log it too so we can find it after.
        logger.info(
            f"CONTRACT OTP (DEV): contract={contract_id} code={code} → {email}"
        )
        result["dev_code"] = code
    return result


async def _consume_contract_otp(contract_id: str, user_id: str, code: str) -> bool:
    now = _now()
    # Latest active code
    rec = await _db.contract_otp_codes.find_one(
        {"contract_id": contract_id, "user_id": user_id, "consumed_at": None},
        sort=[("created_at", -1)],
    )
    if not rec:
        raise HTTPException(status_code=400, detail="No active verification code. Request a new one.")

    try:
        expires = datetime.fromisoformat(rec["expires_at"])
    except Exception:  # noqa: BLE001
        expires = now - timedelta(seconds=1)
    if expires < now:
        raise HTTPException(status_code=400, detail="Verification code expired. Request a new one.")

    attempts = int(rec.get("attempts", 0))
    if attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts. Request a new code.")

    expected = rec["code_hash"]
    got = _code_hash(code.strip(), contract_id)
    if not hmac.compare_digest(expected, got):
        await _db.contract_otp_codes.update_one(
            {"otp_id": rec["otp_id"]},
            {"$inc": {"attempts": 1}},
        )
        raise HTTPException(status_code=400, detail="Incorrect code.")

    await _db.contract_otp_codes.update_one(
        {"otp_id": rec["otp_id"]},
        {"$set": {"consumed_at": now.isoformat()}},
    )
    return True


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def init_router(
    *,
    db,
    get_current_user,
    send_otp_email,
    email_is_configured,
) -> APIRouter:
    global _db, _get_current_user, _send_otp_email, _email_is_configured
    _db = db
    _get_current_user = get_current_user
    _send_otp_email = send_otp_email
    _email_is_configured = email_is_configured

    router = APIRouter(prefix="/api", tags=["legal-contract"])

    # ------- Legal profile -------

    @router.get("/legal/profile")
    async def get_profile(user=Depends(_get_current_user)):
        prof = await _get_or_null_legal_profile(user.user_id)
        return {"profile": prof, "exists": bool(prof)}

    @router.put("/legal/profile")
    async def upsert_profile(
        payload: LegalProfileIn,
        user=Depends(_get_current_user),
    ):
        saved = await _upsert_legal_profile(user.user_id, payload)
        return {"profile": saved, "saved": True}

    # ------- Contracts -------

    @router.post("/contracts/prepare")
    async def prepare_contract(
        body: PrepareContractIn,
        user=Depends(_get_current_user),
    ):
        """Create a DRAFT contract for the current user + project.

        Idempotent per (user, project_id, state='draft'): if a draft already
        exists for the same project we return it instead of stacking drafts.
        """
        now = _now_iso()
        user_id = user.user_id

        if body.project_id:
            existing = await _db.contracts.find_one(
                {
                    "user_id": user_id,
                    "project_id": body.project_id,
                    "state": {"$in": ["draft", "awaiting_signature"]},
                },
                {"_id": 0},
            )
            if existing:
                return {
                    "contract": _contract_state_public(existing),
                    "html": existing.get("rendered_html"),
                }

        snap = await _build_project_snapshot(user_id, body)
        profile = await _get_or_null_legal_profile(user_id) or {}

        rendered_html = _render_template(
            client_name=profile.get("full_name", "[Client]"),
            client_tax_id=profile.get("tax_id", "[Tax ID]"),
            client_address=profile.get("registered_address", "[Registered address]"),
            project_title=snap["project_title"],
            modules=snap["modules"],
            timeline=snap["timeline"],
            price=snap["price"],
            payment_plan=snap["payment_plan"],
        )

        contract_id = f"ctr_{uuid.uuid4().hex[:12]}"
        doc = {
            "contract_id": contract_id,
            "user_id": user_id,
            "project_id": body.project_id,
            "estimate_id": body.estimate_id,
            "state": "draft",
            "template_version": TEMPLATE_VERSION,
            "template_status": TEMPLATE_STATUS,
            "project_title": snap["project_title"],
            "price": snap["price"],
            "timeline": snap["timeline"],
            "modules": snap["modules"],
            "payment_plan": snap["payment_plan"],
            "rendered_html": rendered_html,
            "created_at": now,
            "pdf_status": "not_generated",
        }
        await _db.contracts.insert_one(doc)
        doc.pop("_id", None)
        return {"contract": _contract_state_public(doc), "html": rendered_html}

    @router.get("/contracts/my")
    async def my_contracts(user=Depends(_get_current_user)):
        cur = _db.contracts.find({"user_id": user.user_id}, {"_id": 0}).sort(
            "created_at", -1
        )
        items = [await _c_public_async(c) async for c in cur]
        return {"items": items, "count": len(items)}

    @router.get("/contracts/{contract_id}")
    async def get_contract(contract_id: str, user=Depends(_get_current_user)):
        c = await _db.contracts.find_one(
            {"contract_id": contract_id, "user_id": user.user_id}, {"_id": 0}
        )
        if not c:
            raise HTTPException(status_code=404, detail="Contract not found")
        # Post-sign reads return the immutable snapshot HTML, not the
        # live-rendered draft.
        html = c.get("html_snapshot") or c.get("rendered_html")
        return {
            "contract": _contract_state_public(c),
            "html": html,
            "is_signed": c["state"] == "signed",
        }

    @router.get("/contracts/{contract_id}/html", response_class=HTMLResponse)
    async def get_contract_html(contract_id: str, user=Depends(_get_current_user)):
        c = await _db.contracts.find_one(
            {"contract_id": contract_id, "user_id": user.user_id}, {"_id": 0}
        )
        if not c:
            raise HTTPException(status_code=404, detail="Contract not found")
        html = c.get("html_snapshot") or c.get("rendered_html") or ""
        return HTMLResponse(content=html)

    # ------- Signing -------

    @router.post("/contracts/{contract_id}/sign/request-otp")
    async def request_otp(
        contract_id: str,
        body: SignRequestIn,
        user=Depends(_get_current_user),
    ):
        c = await _db.contracts.find_one(
            {"contract_id": contract_id, "user_id": user.user_id}, {"_id": 0}
        )
        if not c:
            raise HTTPException(status_code=404, detail="Contract not found")
        if c["state"] == "signed":
            raise HTTPException(status_code=409, detail="Contract is already signed")

        # Persist legal profile (this is the "only at signing" collection point).
        await _upsert_legal_profile(user.user_id, body.legal_profile)

        # CONTRACT-P6 — Readiness gate. After profile upsert, profile is
        # complete. Re-check the rest (estimate/scope/price/etc.).
        rd = await _compute_readiness(contract_id, user.user_id)
        if not rd["ready"]:
            raise HTTPException(
                status_code=412,
                detail={"code": "not_ready_to_sign", "missing": rd["missing"]},
            )

        # CONTRACT-P8 — Signature level policy: SES default; AES blocked
        # until external e-sign rail is wired.
        if rd["signature_level_required"] == "aes":
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "aes_required",
                    "message": (
                        "This contract requires an advanced electronic signature "
                        "(AES) which is not yet enabled on this platform. Please "
                        "contact support to arrange enhanced verification."
                    ),
                },
            )

        # Regenerate rendered_html with the updated legal profile + extended
        # composition (CONTRACT-P4 + P5 template).
        profile = await _get_or_null_legal_profile(user.user_id) or {}
        rendered_html = _render_template(
            client_name=profile.get("full_name", "[Client]"),
            client_tax_id=profile.get("tax_id", "[Tax ID]") or "[Tax ID]",
            client_address=profile.get("billing_address")
                or profile.get("registered_address", "[Billing address]"),
            project_title=c.get("project_title", "[Project]"),
            modules=c.get("modules", []),
            timeline=c.get("timeline", "[Timeline]"),
            price=c.get("price", "[Price]"),
            payment_plan=c.get("payment_plan", []),
            client_phone=profile.get("phone"),
            client_email=user.email,
            payment_method=c.get("payment_method"),
            hvl_summary=c.get("hvl_summary"),
            provider_party=os.getenv("EXECUTOR_PARTY", "EVA-X / ATLAS DevOS"),
            provider_address=os.getenv("EXECUTOR_ADDRESS"),
            provider_tax_id=os.getenv("EXECUTOR_TAX_ID"),
            signature_level=rd["signature_level_required"],
        )
        await _db.contracts.update_one(
            {"contract_id": contract_id},
            {"$set": {
                "rendered_html": rendered_html,
                "state": "awaiting_signature",
                "signature_level_required": rd["signature_level_required"],
            }},
        )

        email = user.email or ""
        if not email:
            raise HTTPException(status_code=400, detail="Account has no email; cannot issue OTP.")

        otp = await _issue_contract_otp(contract_id, user.user_id, email)
        return {
            "ok": True,
            "otp": otp,
            "contract_state": "awaiting_signature",
        }

    @router.post("/contracts/{contract_id}/sign/confirm")
    async def confirm_signature(
        contract_id: str,
        body: SignConfirmIn,
        request: Request,
        user=Depends(_get_current_user),
    ):
        c = await _db.contracts.find_one(
            {"contract_id": contract_id, "user_id": user.user_id}, {"_id": 0}
        )
        if not c:
            raise HTTPException(status_code=404, detail="Contract not found")
        if c["state"] == "signed":
            raise HTTPException(status_code=409, detail="Contract is already signed")

        # Enforce all 3 acknowledgements — "evidence package, not a checkbox".
        req_keys = (
            "legal_details_correct",
            "scope_terms_agreed",
            "start_after_payment_understood",
        )
        missing = [k for k in req_keys if not body.acknowledgements.get(k)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing acknowledgements: {', '.join(missing)}",
            )

        # Upsert the legal profile one more time so the snapshot captures the
        # exact values the user saw in the signing UI.
        legal_profile = await _upsert_legal_profile(user.user_id, body.legal_profile)

        # OTP.
        await _consume_contract_otp(contract_id, user.user_id, body.otp_code)

        # Build final snapshot using extended P4+P5 composition.
        sig_level = _required_signature_level(c)
        final_html = _render_template(
            client_name=legal_profile["full_name"],
            client_tax_id=legal_profile.get("tax_id") or "[Tax ID]",
            client_address=legal_profile.get("billing_address")
                or legal_profile.get("registered_address", "[Billing address]"),
            project_title=c.get("project_title", "[Project]"),
            modules=c.get("modules", []),
            timeline=c.get("timeline", "[Timeline]"),
            price=c.get("price", "[Price]"),
            payment_plan=c.get("payment_plan", []),
            client_phone=legal_profile.get("phone"),
            client_email=user.email,
            payment_method=c.get("payment_method"),
            hvl_summary=c.get("hvl_summary"),
            provider_party=os.getenv("EXECUTOR_PARTY", "EVA-X / ATLAS DevOS"),
            provider_address=os.getenv("EXECUTOR_ADDRESS"),
            provider_tax_id=os.getenv("EXECUTOR_TAX_ID"),
            signature_level=sig_level,
        )

        project_snapshot = {
            "project_id": c.get("project_id"),
            "estimate_id": c.get("estimate_id"),
            "project_title": c.get("project_title"),
            "price": c.get("price"),
            "timeline": c.get("timeline"),
            "modules": c.get("modules", []),
            "payment_plan": c.get("payment_plan", []),
            # CONTRACT-P4 — extended composition fields. Best-effort —
            # missing values land in evidence as null and surface as
            # placeholders in template body.
            "payment_method": c.get("payment_method"),
            "hvl_summary": c.get("hvl_summary"),
            "platform_legal_entity": {
                "party": os.getenv("EXECUTOR_PARTY", "EVA-X / ATLAS DevOS"),
                "address": os.getenv("EXECUTOR_ADDRESS"),
                "tax_id": os.getenv("EXECUTOR_TAX_ID"),
                "country": os.getenv("EXECUTOR_COUNTRY"),
                "signatory": os.getenv("EXECUTOR_SIGNATORY"),
            },
            "signature_level": sig_level,
        }
        legal_profile_snapshot = {
            k: v for k, v in legal_profile.items() if not k.startswith("_")
        }
        signed_at = _now_iso()
        composite = json.dumps(
            {
                "contract_id": c["contract_id"],
                "user_id": c["user_id"],
                "template_version": c["template_version"],
                "terms_version": body.terms_version,
                "project_snapshot": project_snapshot,
                "legal_profile_snapshot": legal_profile_snapshot,
                "html_snapshot": final_html,
                "signed_at": signed_at,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        sha = _sha256_hex(composite)

        ip = _client_ip(request)
        ua = _client_ua(request)

        # ---- PDF generation (best-effort, never blocks signing) ----
        pdf_status = "skipped"
        pdf_b64 = None
        try:
            pdf_b64 = await _try_render_pdf(
                final_html,
                contract={
                    "project_title": c.get("project_title"),
                    "sha256_hash": sha,
                    "contract_id": contract_id,
                },
            )
            pdf_status = "generated" if pdf_b64 else "skipped"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"PDF generation failed, HTML fallback kept: {e}")
            pdf_status = "failed"

        # ---- Executor counter-signature (Provider side) ----
        # Per legal pattern: Client signs explicitly via OTP click-wrap; the
        # platform (Provider/Executor) auto-counter-signs at the same moment
        # using a deterministic platform identity. Both signatures are
        # captured in the immutable evidence package — the agreement
        # becomes bilaterally executed.
        executor_signature = {
            "party": "EVA-X / ATLAS DevOS",
            "role": "Provider",
            "tax_id": os.getenv("EXECUTOR_TAX_ID", "[Platform Tax ID — pending]"),
            "registered_address": os.getenv(
                "EXECUTOR_ADDRESS",
                "EVA-X Platform, Operational HQ — pending legal review",
            ),
            "country": os.getenv("EXECUTOR_COUNTRY", "International"),
            "signed_at": signed_at,
            "signature_method": "platform_auto_countersign",
            "signature_authority": os.getenv("EXECUTOR_SIGNATORY", "EVA-X Platform Operator"),
            "signature_hash": _sha256_hex(
                f"executor|{contract_id}|{c['user_id']}|{sha}|{signed_at}"
            ),
        }

        # ---- Persist contract as immutable ----
        await _db.contracts.update_one(
            {"contract_id": contract_id},
            {
                "$set": {
                    "state": "signed",
                    "signed_at": signed_at,
                    "html_snapshot": final_html,
                    "project_snapshot": project_snapshot,
                    "legal_profile_snapshot": legal_profile_snapshot,
                    "terms_version": body.terms_version,
                    "sha256_hash": sha,
                    "pdf_status": pdf_status,
                    "pdf_b64": pdf_b64,
                    "signer": {
                        "ip": ip,
                        "user_agent": ua,
                        "email": user.email,
                        "user_id": user.user_id,
                    },
                    "executor_signature": executor_signature,
                    "fully_executed": True,
                    "signature_level": sig_level,
                }
            },
        )

        # ---- Audit trail row ----
        signature_id = f"sig_{uuid.uuid4().hex[:12]}"
        await _db.contract_signatures.insert_one(
            {
                "signature_id": signature_id,
                "contract_id": contract_id,
                "user_id": user.user_id,
                "accepted": True,
                "full_name": legal_profile["full_name"],
                "tax_id": legal_profile["tax_id"],
                "registered_address": legal_profile["registered_address"],
                "country": legal_profile["country"],
                "phone": legal_profile.get("phone"),
                "ip": ip,
                "user_agent": ua,
                "otp_verified": True,
                "otp_channel": "email",
                "signed_at": signed_at,
                "contract_hash": sha,
                "terms_version": body.terms_version,
                "template_version": c["template_version"],
                "signature_method": "clickwrap_otp",
                "acknowledgements": {k: bool(v) for k, v in body.acknowledgements.items()},
                "executor_signature": executor_signature,
            }
        )

        # ---- Notifications: notify admin + developer that the agreement
        #      is now bilaterally executed. Best-effort; never blocks signing.
        try:
            await _emit_signed_notifications(
                contract_id=contract_id,
                project_id=c.get("project_id"),
                project_title=c.get("project_title") or "Untitled project",
                client_email=user.email or "",
                client_name=legal_profile["full_name"],
                price=c.get("price") or "",
                signed_at=signed_at,
                sha256_hash=sha,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"signed notifications dispatch failed: {e}")

        signed = await _db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
        return {
            "ok": True,
            "contract": _contract_state_public(signed),
            "evidence": {
                "signature_id": signature_id,
                "sha256_hash": sha,
                "signed_at": signed_at,
                "otp_verified": True,
                "pdf_status": pdf_status,
                "fully_executed": True,
                "executor_signature": executor_signature,
            },
        }

    @router.get("/contracts/{contract_id}/evidence")
    async def get_evidence(contract_id: str, user=Depends(_get_current_user)):
        c = await _db.contracts.find_one(
            {"contract_id": contract_id, "user_id": user.user_id}, {"_id": 0}
        )
        if not c:
            raise HTTPException(status_code=404, detail="Contract not found")
        if c["state"] != "signed":
            raise HTTPException(status_code=400, detail="Contract is not signed yet")
        sig = await _db.contract_signatures.find_one(
            {"contract_id": contract_id}, {"_id": 0}, sort=[("signed_at", -1)]
        )
        return {
            "contract": _contract_state_public(c),
            "signature": sig,
            "project_snapshot": c.get("project_snapshot"),
            "legal_profile_snapshot": c.get("legal_profile_snapshot"),
            "terms_version": c.get("terms_version"),
            "template_version": c.get("template_version"),
            "sha256_hash": c.get("sha256_hash"),
            "pdf_status": c.get("pdf_status", "not_generated"),
            "executor_signature": c.get("executor_signature"),
            "fully_executed": bool(c.get("fully_executed", False)),
        }

    # ------- Gate -------

    @router.get("/contracts/gate/{project_id}")
    async def contract_gate(project_id: str, user=Depends(_get_current_user)):
        """Resolve whether a project's contract blocks payment / start.

        Returned states:
          - contract_required       : no contract yet, client must prepare + sign
          - legal_profile_required  : contract exists but client has no legal profile
          - awaiting_signature      : contract prepared, OTP pending or verified
          - signed_payment_unlocked : contract fully signed, payment unlocked
        """
        c = await _db.contracts.find_one(
            {"user_id": user.user_id, "project_id": project_id},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        prof = await _get_or_null_legal_profile(user.user_id)

        if not c:
            return {
                "state": "contract_required",
                "contract_id": None,
                "has_legal_profile": bool(prof),
                "payment_unlocked": False,
            }
        if c["state"] == "signed":
            return {
                "state": "signed_payment_unlocked",
                "contract_id": c["contract_id"],
                "has_legal_profile": True,
                "payment_unlocked": True,
            }
        if not prof:
            return {
                "state": "legal_profile_required",
                "contract_id": c["contract_id"],
                "has_legal_profile": False,
                "payment_unlocked": False,
            }
        return {
            "state": "awaiting_signature",
            "contract_id": c["contract_id"],
            "has_legal_profile": True,
            "payment_unlocked": False,
        }

    # ------- PDF download -------

    @router.get("/contracts/{contract_id}/pdf")
    async def download_contract_pdf(contract_id: str, user=Depends(_get_current_user)):
        """Stream the signed contract as a real PDF file.

        Always returns a PDF (never HTML). If the original PDF was not
        generated at signing time (legacy or render failure), we render
        it lazily NOW from the immutable html_snapshot — the canonical
        evidence stays unchanged.
        """
        import base64
        from fastapi.responses import Response

        c = await _db.contracts.find_one(
            {"contract_id": contract_id, "user_id": user.user_id}, {"_id": 0}
        )
        if not c:
            raise HTTPException(status_code=404, detail="Contract not found")
        if c["state"] != "signed":
            raise HTTPException(
                status_code=400,
                detail="Contract is not signed yet — PDF available after signing.",
            )

        pdf_b64 = c.get("pdf_b64")
        if not pdf_b64:
            # Lazy render from immutable html_snapshot. Persist the bytes so
            # subsequent downloads are O(1).
            html = c.get("html_snapshot") or c.get("rendered_html") or ""
            pdf_b64 = await _try_render_pdf(
                html,
                contract={
                    "project_title": c.get("project_title"),
                    "sha256_hash": c.get("sha256_hash"),
                    "contract_id": contract_id,
                },
            )
            if pdf_b64:
                await _db.contracts.update_one(
                    {"contract_id": contract_id},
                    {"$set": {"pdf_b64": pdf_b64, "pdf_status": "generated"}},
                )

        if not pdf_b64:
            raise HTTPException(
                status_code=503,
                detail="PDF render unavailable on this host; use /html endpoint.",
            )

        try:
            pdf_bytes = base64.b64decode(pdf_b64)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=500, detail="Corrupt PDF blob")

        safe_title = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in (c.get("project_title") or "agreement")
        )[:60]
        filename = f"agreement_{safe_title}_{contract_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Contract-Sha256": c.get("sha256_hash") or "",
            },
        )

    # ------- ZIP bulk export (every signed contract + evidence JSON) -------

    @router.get("/contracts/exports/zip")
    async def export_contracts_zip(user=Depends(_get_current_user)):
        """Download all signed contracts as a single ZIP archive.

        Layout:
          /<contract_id>/agreement.pdf      ← if rendered
          /<contract_id>/agreement.html     ← always (immutable html_snapshot)
          /<contract_id>/evidence.json      ← signature + project/legal snapshots
          manifest.json                     ← top-level inventory + sha256 list
        """
        import base64
        import io
        import json as _json
        import zipfile
        from fastapi.responses import Response

        cur = _db.contracts.find(
            {"user_id": user.user_id, "state": "signed"}, {"_id": 0},
        ).sort("signed_at", -1)
        contracts = [doc async for doc in cur]
        if not contracts:
            raise HTTPException(status_code=404, detail="No signed contracts to export.")

        buf = io.BytesIO()
        manifest: List[Dict[str, Any]] = []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for c in contracts:
                cid = c["contract_id"]
                title = c.get("project_title") or "agreement"
                html = c.get("html_snapshot") or c.get("rendered_html") or ""
                if html:
                    zf.writestr(f"{cid}/agreement.html", html)
                pdf_b64 = c.get("pdf_b64")
                if pdf_b64:
                    try:
                        zf.writestr(f"{cid}/agreement.pdf",
                                    base64.b64decode(pdf_b64))
                    except Exception:  # noqa: BLE001
                        pass
                sig = await _db.contract_signatures.find_one(
                    {"contract_id": cid}, {"_id": 0},
                    sort=[("signed_at", -1)],
                )
                evidence = {
                    "contract_id": cid,
                    "project_title": title,
                    "signed_at": c.get("signed_at"),
                    "sha256_hash": c.get("sha256_hash"),
                    "template_version": c.get("template_version"),
                    "terms_version": c.get("terms_version"),
                    "project_snapshot": c.get("project_snapshot"),
                    "legal_profile_snapshot": c.get("legal_profile_snapshot"),
                    "signer": c.get("signer"),
                    "executor_signature": c.get("executor_signature"),
                    "fully_executed": c.get("fully_executed", False),
                    "signature_audit": sig,
                }
                zf.writestr(
                    f"{cid}/evidence.json",
                    _json.dumps(evidence, indent=2, ensure_ascii=False, default=str),
                )
                manifest.append({
                    "contract_id": cid,
                    "project_title": title,
                    "signed_at": c.get("signed_at"),
                    "sha256_hash": c.get("sha256_hash"),
                    "has_pdf": bool(pdf_b64),
                })
            zf.writestr(
                "manifest.json",
                _json.dumps(
                    {
                        "user_id": user.user_id,
                        "exported_at": _now_iso(),
                        "count": len(manifest),
                        "items": manifest,
                    },
                    indent=2, ensure_ascii=False,
                ),
            )
        filename = f"my_agreements_{user.user_id}_{int(_now().timestamp())}.zip"
        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    # ------- Reminder sweep (operational endpoint, used by event_engine) -------

    @router.post("/contracts/_reminders/sweep")
    async def reminders_sweep(user=Depends(_get_current_user)):
        """Send reminder emails for awaiting_signature contracts older
        than 24h. Idempotent: each cadence (24h / 48h / 96h) sends once.

        Admin-only. Manually triggers a sweep; the background loop runs
        every 6 hours automatically.
        """
        roles = set(getattr(user, "roles", []) or [])
        if "admin" not in roles and getattr(user, "role", "") != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        result = await _run_reminder_sweep()
        return result

    # ------- CONTRACT-P6 Signature Readiness Gate -------

    @router.get("/contracts/{contract_id}/readiness")
    async def signature_readiness(contract_id: str, user=Depends(_get_current_user)):
        """Return a hard checklist that MUST be all-true before the
        client can sign. Frontend uses this to drive the sign CTA and
        show the user what's missing; backend re-checks the same on
        request-otp / confirm and returns 412 if anything is false.
        """
        result = await _compute_readiness(contract_id, user.user_id)
        return result

    # ------- CONTRACT-P7 Data export (GDPR-style "give me my data") -------

    @router.get("/legal/profile/export")
    async def export_legal_profile(user=Depends(_get_current_user)):
        """Return everything we hold about this user's legal identity:
        profile snapshot, every contract signed, the signature evidence
        rows. Sensitive fields decrypted only for the owner."""
        prof = await _get_or_null_legal_profile(user.user_id) or {}
        contracts = [
            _contract_state_public(c)
            async for c in _db.contracts.find(
                {"user_id": user.user_id}, {"_id": 0}
            ).sort("created_at", -1)
        ]
        sigs = [
            sig
            async for sig in _db.contract_signatures.find(
                {"user_id": user.user_id}, {"_id": 0}
            ).sort("signed_at", -1)
        ]
        return {
            "user_id": user.user_id,
            "email": user.email,
            "exported_at": _now_iso(),
            "legal_profile": prof,
            "contracts": contracts,
            "signatures": sigs,
            "note": (
                "This is the full dataset that the platform holds about your "
                "legal identity and your signed agreements. "
                "Sensitive fields (tax_id, company_registration_number) are "
                "decrypted for you, the owner. Signed contracts and their "
                "evidence rows are retained as required by law and cannot be "
                "redacted without a separate deletion request."
            ),
        }

    # ------- CONTRACT-P7 Deletion request (signed contracts are retained) -------

    @router.post("/legal/profile/delete-request")
    async def request_profile_delete(user=Depends(_get_current_user)):
        """Open an erasure request. The legal profile fields are cleared
        immediately for unsigned context; signed contracts and their
        evidence rows are retained per Section 18 retention rule.

        Marks the profile as `deletion_requested` and writes an audit row;
        actual processing follows the retention policy (admin reviews via
        /api/admin/legal/deletion-requests once that surface is live).
        """
        await _db.client_legal_profiles.update_one(
            {"user_id": user.user_id},
            {"$set": {
                "deletion_requested_at": _now_iso(),
                "deletion_state": "open",
                # Clear non-signed sensitive plaintext fields immediately.
                "tax_id_enc": None,
                "company_registration_number_enc": None,
            }},
        )
        await _db.legal_access_audit.insert_one({
            "audit_id": f"laa_{uuid.uuid4().hex[:12]}",
            "actor_user_id": user.user_id,
            "actor_role": getattr(user, "role", "client"),
            "subject_user_id": user.user_id,
            "reason": "self_delete_request",
            "at": _now_iso(),
        })
        return {"ok": True, "state": "open",
                "note": "Erasure request opened. Signed contract evidence "
                        "rows are retained as required by law."}

    # ------- CONTRACT-P7 Admin oversight surface --------------------------
    # Read-only by default. Every admin read of someone else's legal data
    # leaves a row in `legal_access_audit` (the owner is excluded from
    # logging — they're reading their own data).
    # ----------------------------------------------------------------------

    def _is_admin(u) -> bool:
        try:
            roles = set(getattr(u, "roles", []) or [])
        except Exception:
            roles = set()
        return "admin" in roles or getattr(u, "role", "") == "admin"

    @router.get("/admin/legal/profile/{target_user_id}")
    async def admin_get_legal_profile(
        target_user_id: str,
        reason: str = "admin_review",
        user=Depends(_get_current_user),
    ):
        """Read another user's legal profile. Logs the access."""
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        prof = await _get_or_null_legal_profile(target_user_id)
        if not prof:
            raise HTTPException(status_code=404, detail="No legal profile for that user")
        await _audit_legal_access(
            actor_user_id=user.user_id,
            actor_role=getattr(user, "role", "admin"),
            subject_user_id=target_user_id,
            reason=reason,
        )
        return {"profile": prof, "subject_user_id": target_user_id}

    @router.get("/admin/legal/deletion-requests")
    async def admin_list_deletion_requests(
        state: Optional[str] = "open",
        limit: int = 100,
        user=Depends(_get_current_user),
    ):
        """List legal-profile erasure requests. Default = open ones."""
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        q: Dict[str, Any] = {"deletion_requested_at": {"$exists": True}}
        if state:
            q["deletion_state"] = state
        cur = _db.client_legal_profiles.find(q, {"_id": 0}).sort(
            "deletion_requested_at", -1
        ).limit(max(1, min(int(limit), 500)))
        items: List[Dict[str, Any]] = []
        async for d in cur:
            items.append({
                "user_id": d.get("user_id"),
                "full_name": d.get("full_name"),
                "legal_type": d.get("legal_type"),
                "country": d.get("country"),
                "deletion_requested_at": d.get("deletion_requested_at"),
                "deletion_state": d.get("deletion_state"),
                "deletion_resolved_at": d.get("deletion_resolved_at"),
                "deletion_resolution": d.get("deletion_resolution"),
            })
        return {"items": items, "count": len(items)}

    @router.post("/admin/legal/deletion-requests/{target_user_id}/resolve")
    async def admin_resolve_deletion_request(
        target_user_id: str,
        body: Dict[str, Any],
        user=Depends(_get_current_user),
    ):
        """Mark an erasure request as resolved.

        body = { "resolution": "redacted" | "rejected" | "retained_under_law",
                 "note": "<free text>" }
        Signed-contract evidence rows are NEVER deleted from here — the
        platform retains them per Section 18.
        """
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        resolution = (body or {}).get("resolution") or "retained_under_law"
        if resolution not in ("redacted", "rejected", "retained_under_law"):
            raise HTTPException(status_code=422, detail="Invalid resolution code")
        note = (body or {}).get("note") or ""
        upd = await _db.client_legal_profiles.update_one(
            {"user_id": target_user_id,
             "deletion_state": "open"},
            {"$set": {
                "deletion_state": "resolved",
                "deletion_resolved_at": _now_iso(),
                "deletion_resolved_by": user.user_id,
                "deletion_resolution": resolution,
                "deletion_resolution_note": note,
            }},
        )
        if upd.matched_count == 0:
            raise HTTPException(status_code=404, detail="No open deletion request for that user")
        await _audit_legal_access(
            actor_user_id=user.user_id,
            actor_role=getattr(user, "role", "admin"),
            subject_user_id=target_user_id,
            reason=f"deletion_resolved:{resolution}",
        )
        return {"ok": True, "resolution": resolution}

    @router.get("/admin/legal/access-log")
    async def admin_access_log(
        subject_user_id: Optional[str] = None,
        limit: int = 100,
        user=Depends(_get_current_user),
    ):
        """Paginated read of the legal-data access audit trail."""
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        q: Dict[str, Any] = {}
        if subject_user_id:
            q["subject_user_id"] = subject_user_id
        cur = _db.legal_access_audit.find(q, {"_id": 0}).sort(
            "at", -1,
        ).limit(max(1, min(int(limit), 500)))
        rows = [r async for r in cur]
        return {"items": rows, "count": len(rows)}

    @router.get("/admin/legal/contracts")
    async def admin_list_contracts(
        state: Optional[str] = None,
        limit: int = 100,
        user=Depends(_get_current_user),
    ):
        """Admin view: list contracts across all users (optionally filtered).
        Heavy fields (html snapshots, pdf blobs) are stripped.
        """
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        q: Dict[str, Any] = {}
        if state:
            q["state"] = state
        cur = _db.contracts.find(q, {
            "_id": 0,
            "html_snapshot": 0,
            "rendered_html": 0,
            "pdf_b64": 0,
        }).sort("created_at", -1).limit(max(1, min(int(limit), 500)))
        items = [_contract_state_public(c) async for c in cur]
        return {"items": items, "count": len(items)}

    return router


# ---------------------------------------------------------------------------
# CONTRACT-P6 Readiness gate — single source of truth
# ---------------------------------------------------------------------------


async def _compute_readiness(contract_id: str, user_id: str) -> Dict[str, Any]:
    """Return a deterministic checklist + a boolean `ready` flag.

    Backend-truth. Both UI and the sign endpoints consume this.
    """
    contract = await _db.contracts.find_one(
        {"contract_id": contract_id, "user_id": user_id}, {"_id": 0}
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    profile = await _get_or_null_legal_profile(user_id) or {}

    checks = {
        "legal_profile_completed": bool(
            profile.get("legal_type")
            and profile.get("first_name")
            and profile.get("last_name")
            and profile.get("billing_address")
        ),
        "phone_present": bool(profile.get("phone")),
        "billing_address_present": bool(profile.get("billing_address")),
        "country_present": bool(profile.get("country")),
        "company_block_complete_if_company": (
            profile.get("legal_type") != "company"
            or (bool(profile.get("company_name"))
                and bool(profile.get("company_registration_number")))
        ),
        "estimate_present": bool(
            contract.get("estimate_id")
            or contract.get("price")
            or contract.get("project_id")
        ),
        "scope_present": bool(contract.get("modules") or contract.get("project_id")),
        "price_present": bool(contract.get("price")),
        "contract_generated": bool(contract.get("rendered_html")),
        "template_version_locked": bool(contract.get("template_version")),
        "not_already_signed": contract["state"] != "signed",
    }

    missing = [k for k, v in checks.items() if not v]
    return {
        "contract_id": contract_id,
        "ready": len(missing) == 0,
        "checks": checks,
        "missing": missing,
        "verification_level": profile.get("verification_level", "basic"),
        "signature_level_required": _required_signature_level(contract),
    }


def _required_signature_level(contract: Dict[str, Any]) -> str:
    """CONTRACT-P8 — Signature Level Policy.

    Default = SES (simple electronic signature). For high-value
    contracts above `CONTRACT_AES_THRESHOLD_USD`, the policy switches
    to AES (advanced electronic signature) which is not yet wired and
    will surface 503 until the external e-sign provider is connected.
    """
    try:
        threshold = float(os.getenv("CONTRACT_AES_THRESHOLD_USD", "0") or 0)
    except Exception:
        threshold = 0.0
    if threshold <= 0:
        return "ses"
    try:
        # Strip non-numeric characters from price (e.g. "$1,500" → 1500).
        raw = str(contract.get("price") or "0")
        digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
        amount = float(digits or 0)
    except Exception:
        amount = 0.0
    return "aes" if amount >= threshold else "ses"


# ---------------------------------------------------------------------------
# Notifications + reminder daemon (Phase 2 — operational reach)
# ---------------------------------------------------------------------------


async def _emit_signed_notifications(
    *,
    contract_id: str,
    project_id: Optional[str],
    project_title: str,
    client_email: str,
    client_name: str,
    price: str,
    signed_at: str,
    sha256_hash: str,
) -> None:
    """Fan-out: in-app notifications for admins + assigned developers +
    a confirmation row for the client themselves.

    All writes go through the existing `notifications` collection
    (consumed by `/api/notifications/my` + push_sender).

    i18n (Phase i18n): we resolve each recipient's `language` and use
    `notif.contract_signed_{client|admin|dev}.{title|body}` from
    `i18n_backend`. Fallback to English if i18n module / key missing.
    """
    try:
        from i18n_backend import t as _t
    except Exception:
        _t = lambda k, lang=None, **kw: k  # noqa: E731 — graceful degrade

    async def _resolve_lang(uid: str) -> str:
        try:
            u = await _db.users.find_one({"user_id": uid}, {"_id": 0, "language": 1})
            lg = ((u or {}).get("language") or "").strip().lower().split("-", 1)[0]
            return lg if lg in ("en", "uk") else "en"
        except Exception:
            return "en"

    base = {
        "kind": "contract.signed",
        "created_at": _now_iso(),
        "read": False,
        "data": {
            "contract_id": contract_id,
            "project_id": project_id,
            "sha256_hash": (sha256_hash or "")[:16],
            "signed_at": signed_at,
        },
    }
    price_suffix = f" ({price})" if price else ""

    rows: List[Dict[str, Any]] = []

    # 1) Client gets a self-confirmation
    client_user = await _db.users.find_one(
        {"email": client_email}, {"_id": 0, "user_id": 1},
    ) if client_email else None
    if client_user:
        lg = await _resolve_lang(client_user["user_id"])
        rows.append({
            **base,
            "notification_id": f"ntf_{uuid.uuid4().hex[:12]}",
            "user_id": client_user["user_id"],
            "title": _t("notif.contract_signed_client.title", lg, project=project_title),
            "body":  _t("notif.contract_signed_client.body",  lg, project=project_title),
        })

    # 2) Every admin
    admins_cur = _db.users.find(
        {"$or": [{"role": "admin"}, {"roles": "admin"}]},
        {"_id": 0, "user_id": 1},
    )
    async for u in admins_cur:
        lg = await _resolve_lang(u["user_id"])
        rows.append({
            **base,
            "notification_id": f"ntf_{uuid.uuid4().hex[:12]}",
            "user_id": u["user_id"],
            "title": _t("notif.contract_signed_admin.title", lg),
            "body":  _t("notif.contract_signed_admin.body",  lg,
                         client=client_name, project=project_title, price_suffix=price_suffix),
        })

    # 3) Developer(s) assigned to this project (if any)
    if project_id:
        proj = await _db.projects.find_one(
            {"project_id": project_id},
            {"_id": 0, "developer_id": 1, "team": 1, "modules": 1},
        )
        dev_ids: set = set()
        if proj:
            if proj.get("developer_id"):
                dev_ids.add(proj["developer_id"])
            for member in (proj.get("team") or []):
                if isinstance(member, dict) and member.get("user_id"):
                    dev_ids.add(member["user_id"])
            for mod in (proj.get("modules") or []):
                if isinstance(mod, dict) and mod.get("developer_id"):
                    dev_ids.add(mod["developer_id"])
        for dev_id in dev_ids:
            lg = await _resolve_lang(dev_id)
            rows.append({
                **base,
                "notification_id": f"ntf_{uuid.uuid4().hex[:12]}",
                "user_id": dev_id,
                "title": _t("notif.contract_signed_dev.title", lg),
                "body":  _t("notif.contract_signed_dev.body",  lg, project=project_title),
            })

    if rows:
        await _db.notifications.insert_many(rows)
        logger.info(
            "contract.signed notifications fanned out: %d recipients (contract=%s)",
            len(rows), contract_id,
        )


# Reminder cadence (hours since prepared) → marker key in contract doc.
_REMINDER_CADENCE = [
    (24, "reminder_24h_sent_at"),
    (48, "reminder_48h_sent_at"),
    (96, "reminder_96h_sent_at"),
]


async def _run_reminder_sweep() -> Dict[str, Any]:
    """Walk every awaiting_signature contract, emit a reminder notification
    at the 24h / 48h / 96h mark (each cadence at-most-once).
    """
    now = _now()
    counts = {"awaiting": 0, "reminded_24h": 0, "reminded_48h": 0,
              "reminded_96h": 0, "errors": 0}

    cur = _db.contracts.find(
        {"state": "awaiting_signature"}, {"_id": 0},
    )
    async for c in cur:
        counts["awaiting"] += 1
        try:
            created_iso = c.get("created_at") or _now_iso()
            try:
                created = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
            except Exception:
                continue
            age_h = (now - created).total_seconds() / 3600.0
            for threshold_h, marker in _REMINDER_CADENCE:
                if age_h >= threshold_h and not c.get(marker):
                    await _emit_reminder_notification(c, threshold_h)
                    await _db.contracts.update_one(
                        {"contract_id": c["contract_id"]},
                        {"$set": {marker: _now_iso()}},
                    )
                    counts[f"reminded_{threshold_h}h"] += 1
        except Exception as e:  # noqa: BLE001
            counts["errors"] += 1
            logger.warning(f"reminder sweep error for {c.get('contract_id')}: {e}")

    logger.info("REMINDER SWEEP: %s", counts)
    return counts


async def _emit_reminder_notification(
    contract: Dict[str, Any], threshold_h: int,
) -> None:
    """Emit contract-reminder notification, localized to recipient's language."""
    try:
        from i18n_backend import t as _t
    except Exception:
        _t = lambda k, lang=None, **kw: k  # noqa: E731

    uid = contract["user_id"]
    try:
        u = await _db.users.find_one({"user_id": uid}, {"_id": 0, "language": 1})
        lg = ((u or {}).get("language") or "").strip().lower().split("-", 1)[0]
        if lg not in ("en", "uk"):
            lg = "en"
    except Exception:
        lg = "en"

    project_title = contract.get("project_title") or "your project"
    title = _t("notif.contract_reminder.title", lg, project=project_title)
    body  = _t("notif.contract_reminder.body",  lg, project=project_title)
    row = {
        "notification_id": f"ntf_{uuid.uuid4().hex[:12]}",
        "user_id": uid,
        "kind": f"contract.reminder.{threshold_h}h",
        "title": title,
        "body": body,
        "created_at": _now_iso(),
        "read": False,
        "data": {
            "contract_id": contract["contract_id"],
            "project_id": contract.get("project_id"),
            "project_title": project_title,
        },
    }
    await _db.notifications.insert_one(row)


async def contract_reminder_loop(db) -> None:
    """Background loop — called once from server.py at boot.
    Sweeps every `CONTRACT_REMINDER_INTERVAL_SEC` seconds (default 6h).
    """
    import asyncio
    global _db
    if _db is None:
        _db = db
    interval = int(os.getenv("CONTRACT_REMINDER_INTERVAL_SEC", "21600") or 21600)
    if interval <= 0:
        logger.info("CONTRACT REMINDER LOOP: disabled (interval<=0)")
        return
    logger.info("CONTRACT REMINDER LOOP: started (interval %ds)", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            await _run_reminder_sweep()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("CONTRACT REMINDER LOOP: cycle failed (will retry)")


async def _try_render_pdf(html: str, *, contract: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Production PDF rendering via ReportLab (pure Python, no system deps).

    Strategy:
      1. Use ReportLab Platypus — converts our contract HTML structure
         into a properly paginated, multi-page PDF document.
      2. Header carries the project title + EVA-X branding.
      3. Footer carries page number + sha256 hint (truncated) so the printed
         PDF is self-evidencing.
      4. Bilingual-safe: all string handling is UTF-8 throughout.

    Returns base64-encoded PDF bytes. On unexpected failure logs and
    returns None — caller records `pdf_status='failed'` and keeps
    html_snapshot + sha256 as source of truth.

    The function never blocks signing (caller wraps in try/except).
    """
    try:
        import asyncio
        import base64
        import io
        import re

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                BaseDocTemplate, Frame, PageTemplate, Paragraph,
                Spacer, ListFlowable, ListItem, KeepTogether,
            )
        except Exception:  # noqa: BLE001 — defensive even though we just installed it
            logger.warning("reportlab not importable; skipping PDF render")
            return None

        # ---- Parse our contract HTML into a list of (kind, text) blocks ----
        # We accept the same subset our Expo preview renders: h1, h2, p, li, ul/ol.
        cleaned = re.sub(r"<!--.*?-->", "", html or "", flags=re.S)
        cleaned = re.sub(r"<section[^>]*>|</section>", "", cleaned)
        # ReportLab Paragraph supports <b>, <i>, <font>; strip everything else.
        def _inline(s: str) -> str:
            s = re.sub(r"</?(?:span|em|strong)[^>]*>", "", s)
            # keep <b>, <i> as-is
            s = re.sub(r"<br\s*/?>", "<br/>", s)
            return s.strip()

        block_re = re.compile(
            r"<(h1|h2|p|ul|ol)([^>]*)>(.*?)</\1>", re.S | re.I,
        )
        li_re = re.compile(r"<li[^>]*>(.*?)</li>", re.S | re.I)

        blocks: List[Dict[str, Any]] = []
        for m in block_re.finditer(cleaned):
            tag = m.group(1).lower()
            attrs = (m.group(2) or "")
            inner = m.group(3) or ""
            if tag in ("ul", "ol"):
                items = [_inline(re.sub(r"<[^>]+>", "", li_re_inner)) if False else _inline(li_re_inner)
                         for li_re_inner in li_re.findall(inner)]
                items = [x for x in items if x]
                if items:
                    blocks.append({"kind": tag, "items": items})
            else:
                text = _inline(inner)
                if not text:
                    continue
                kind = tag
                if tag == "p" and "class=\"meta\"" in attrs:
                    kind = "meta"
                if tag == "p" and "class=\"placeholder\"" in attrs:
                    kind = "placeholder"
                blocks.append({"kind": kind, "text": text})

        # ---- Build PDF ----
        project_title = (contract or {}).get("project_title") or "Service Agreement"
        sha_hint = ((contract or {}).get("sha256_hash") or "")[:12]
        contract_id_hint = ((contract or {}).get("contract_id") or "")[:18]

        buf = io.BytesIO()

        def _on_page(canvas, doc):
            canvas.saveState()
            # Header
            canvas.setFont("Helvetica-Bold", 9)
            canvas.setFillGray(0.35)
            canvas.drawString(20 * mm, A4[1] - 12 * mm, "EVA-X · ATLAS DevOS")
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(A4[0] - 20 * mm, A4[1] - 12 * mm,
                                   project_title[:60])
            canvas.setStrokeGray(0.85)
            canvas.line(20 * mm, A4[1] - 14 * mm,
                        A4[0] - 20 * mm, A4[1] - 14 * mm)
            # Footer
            canvas.setFont("Helvetica", 7)
            canvas.setFillGray(0.45)
            footer = (f"{contract_id_hint}  ·  sha256:{sha_hint}…  "
                      f"·  Page {doc.page}")
            canvas.drawCentredString(A4[0] / 2, 10 * mm, footer)
            canvas.restoreState()

        def _build() -> bytes:
            ss = getSampleStyleSheet()
            h1 = ParagraphStyle(
                "H1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                fontSize=18, leading=22, spaceAfter=6, textColor="#0F172A",
            )
            h2 = ParagraphStyle(
                "H2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                fontSize=12, leading=16, spaceBefore=10, spaceAfter=4,
                textColor="#0F172A",
            )
            body = ParagraphStyle(
                "Body", parent=ss["BodyText"], fontName="Helvetica",
                fontSize=10, leading=14, spaceAfter=4, textColor="#0F172A",
            )
            meta = ParagraphStyle(
                "Meta", parent=body, fontName="Helvetica-Oblique",
                fontSize=8, textColor="#64748B",
            )
            placeholder = ParagraphStyle(
                "Placeholder", parent=body, fontName="Helvetica-Oblique",
                textColor="#94A3B8",
            )

            doc = BaseDocTemplate(
                buf, pagesize=A4,
                leftMargin=20 * mm, rightMargin=20 * mm,
                topMargin=22 * mm, bottomMargin=18 * mm,
                title=project_title, author="EVA-X / ATLAS DevOS",
            )
            frame = Frame(
                doc.leftMargin, doc.bottomMargin,
                doc.width, doc.height, showBoundary=0,
            )
            doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_on_page)])

            story: List[Any] = []
            for blk in blocks:
                k = blk["kind"]
                if k == "h1":
                    story.append(Paragraph(blk["text"], h1))
                elif k == "h2":
                    story.append(Paragraph(blk["text"], h2))
                elif k == "meta":
                    story.append(Paragraph(blk["text"], meta))
                elif k == "placeholder":
                    story.append(Paragraph(blk["text"], placeholder))
                elif k == "p":
                    story.append(Paragraph(blk["text"], body))
                elif k in ("ul", "ol"):
                    li = [ListItem(Paragraph(t, body), leftIndent=8)
                          for t in blk["items"]]
                    story.append(ListFlowable(
                        li,
                        bulletType="bullet" if k == "ul" else "1",
                        leftIndent=14, spaceBefore=2, spaceAfter=4,
                    ))

            # If parsing produced nothing, emit a single placeholder so the PDF
            # isn't blank — html_snapshot remains canonical anyway.
            if not story:
                story.append(Paragraph(
                    "(Contract body — see html_snapshot for full text)",
                    placeholder,
                ))
            doc.build(story)
            return buf.getvalue()

        pdf_bytes = await asyncio.to_thread(_build)
        return base64.b64encode(pdf_bytes).decode("ascii")
    except Exception as e:  # noqa: BLE001 — last-resort safety
        logger.warning(f"reportlab render failed: {e}")
        return None


# Small helper for async generator -> list with public projection.
async def _c_public_async(c: Dict[str, Any]) -> Dict[str, Any]:
    return _contract_state_public(c)
