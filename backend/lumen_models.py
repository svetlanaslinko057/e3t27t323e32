"""
LUMEN core domain models — Sprint 1 / Phase 0.

These Pydantic schemas define the canonical structure of the LUMEN investment
platform's persistence layer. They are intentionally minimal and contain NO
business logic, NO validation beyond field types, and NO payment / KYC / approval
flows. Those will arrive in Sprint 2 (Investment Core) and beyond.

Collections owned by this module:

    lumen_assets               — investable assets (real estate, vehicles, etc.)
    lumen_investment_rounds    — fundraising rounds attached to an asset
    lumen_investor_intents     — investor declared intent to invest (pre-KYC)
    lumen_investments          — confirmed investments (post-payment)
    lumen_ownerships           — units/shares ledger per (investor, asset)
    lumen_investor_profiles    — KYC / tax / IBAN / risk profile per user

All identifiers are UUID v4 strings. All datetimes are timezone-aware UTC.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Asset — investable real-world asset on the LUMEN platform
# ──────────────────────────────────────────────────────────────────────────────

AssetStatus = Literal["draft", "open", "funded", "closed", "archived"]
AssetCategory = Literal[
    "real_estate",
    "vehicle",
    "equipment",
    "business",
    "agriculture",
    "other",
]


class LumenAsset(BaseModel):
    """Investable asset. Economics fields mirror /api/economics/spec.

    Canonical field set aligned with the Sprint 2 Domain Audit. Live Mongo
    documents seeded by lumen_api use legacy aliases — the mapping is:

        category        == asset_type   (audit name)
        round_target    -> target_amount (canonical)
        raised          -> raised_amount (canonical)
        target_yield    == expected_yield (audit name)
        horizon_months  -> term_months   (canonical)

    The investment engine writes BOTH canonical and legacy keys so the
    existing web frontend keeps working without changes.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    title: str
    category: AssetCategory = "real_estate"   # a.k.a. asset_type
    status: AssetStatus = "draft"
    description: Optional[str] = None
    cover_url: Optional[str] = None
    location: Optional[str] = None
    spv_label: Optional[str] = None
    featured: bool = False

    # Funding
    target_amount: float = 0.0         # total raise target in fiat (UAH); legacy: round_target
    raised_amount: float = 0.0         # auto-updated by Investment Engine; legacy: raised
    min_ticket: float = 0.0            # minimum ticket per investor
    investors_count: int = 0           # distinct investors with active investments
    term_months: int = 0               # investment horizon; legacy: horizon_months

    # Economics (parity with lumenEconomics / lumen-economics libraries)
    target_yield: float = 0.0          # annual gross yield, % (audit: expected_yield)
    rental_share: float = 0.0          # share of revenue distributed to investors (0..1)
    opex_rate: float = 0.0             # operating expenses ratio (0..1)
    tax_rate: float = 0.0              # tax rate on distributions (0..1)
    platform_fee: float = 0.0          # LUMEN platform fee (0..1)

    # Lifecycle
    open_date: Optional[datetime] = None
    close_date: Optional[datetime] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Investment Round — fundraising window attached to an asset
# ──────────────────────────────────────────────────────────────────────────────

RoundStatus = Literal["scheduled", "open", "closed", "cancelled"]


class LumenInvestmentRound(BaseModel):
    """Fundraising round. Canonical names per Sprint 2 Domain Audit."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    asset_id: str
    round_number: int = 1
    round_name: Optional[str] = None        # e.g. "Раунд I"
    status: RoundStatus = "scheduled"

    target_amount: float = 0.0
    raised_amount: float = 0.0
    minimum_ticket: float = 0.0
    max_ticket: Optional[float] = None

    open_at: Optional[datetime] = None
    close_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Investor Intent — declared interest BEFORE confirmed payment
# ──────────────────────────────────────────────────────────────────────────────

IntentStatus = Literal[
    "submitted",     # investor created the intent
    "under_review",  # admin / compliance is reviewing
    "approved",      # admin approved → investor may proceed to payment
    "rejected",      # admin rejected (KYC / limits / availability)
    "expired",       # round closed / TTL hit before payment
    "converted",     # payment received → became a LumenInvestment
    "cancelled",     # investor cancelled
]


class LumenInvestorIntent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    asset_id: str
    round_id: Optional[str] = None
    investor_id: str           # users.user_id

    amount: float              # requested ticket size
    status: IntentStatus = "submitted"
    note: Optional[str] = None
    admin_note: Optional[str] = None

    submitted_at: datetime = Field(default_factory=_utcnow)
    reviewed_at: Optional[datetime] = None
    reviewer_id: Optional[str] = None
    converted_investment_id: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Investment — confirmed, paid investment
# ──────────────────────────────────────────────────────────────────────────────

InvestmentStatus = Literal[
    "pending_payment",
    "kyc_pending",       # Sprint 3 soft-mode: approved intent awaiting investor KYC
    "contract_pending",  # Sprint 4: KYC ok, awaiting contract signature
    "active",
    "matured",
    "refunded",
    "cancelled",
]


class LumenInvestment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    asset_id: str
    round_id: Optional[str] = None
    investor_id: str
    intent_id: Optional[str] = None

    amount: float                       # invested principal (fiat)
    units: float = 0.0                  # ownership units issued
    ownership_percent: float = 0.0      # % of asset pool at issuance

    status: InvestmentStatus = "pending_payment"
    payment_reference: Optional[str] = None
    contract_id: Optional[str] = None   # link to legal contract (Phase 4)

    invested_at: Optional[datetime] = None
    matured_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Ownership — units ledger (the source of truth for "who owns what")
# ──────────────────────────────────────────────────────────────────────────────

class LumenOwnership(BaseModel):
    """Aggregated ownership record per (investor, asset).

    This is the source of truth for all future yield distribution, voting,
    secondary-market transfers, and reporting. No accruals / payouts logic
    lives here yet (Sprint 2+).
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    investor_id: str
    asset_id: str
    investment_id: Optional[str] = None     # last contributing investment

    units: float = 0.0
    ownership_percent: float = 0.0          # current % of asset pool

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 6. Investor Profile — KYC / tax / payout details (per user)
# ──────────────────────────────────────────────────────────────────────────────

KycStatus = Literal[
    "not_started",
    "draft",          # investor started filling the profile
    "submitted",      # investor submitted for review
    "under_review",   # compliance picked it up
    "approved",
    "rejected",
    "expired",
]

AccreditationStatus = Literal[
    "none",
    "self_declared",
    "verified",
    "expired",
]


class LumenInvestorProfile(BaseModel):
    """Per-user profile holding KYC, tax, banking, and risk classification.

    Sprint 1 ships only the schema — no validation, no document upload,
    no provider integrations. Fields default to empty/none so existing
    users remain valid.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    user_id: str                            # FK → users.user_id (unique)

    # Identity
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None     # ISO date
    phone: Optional[str] = None
    country: Optional[str] = None           # citizenship, ISO 3166-1 alpha-2
    residency_country: Optional[str] = None # tax residency, ISO 3166-1 alpha-2
    tax_id: Optional[str] = None            # e.g. RNOKPP (UA)

    # Banking
    iban: Optional[str] = None
    bank_name: Optional[str] = None
    bank_country: Optional[str] = None

    # Risk / accreditation
    risk_profile: Literal["conservative", "balanced", "aggressive", "unknown"] = "unknown"
    accreditation_status: AccreditationStatus = "none"
    kyc_status: KycStatus = "not_started"
    kyc_reviewed_at: Optional[datetime] = None
    kyc_reviewer_id: Optional[str] = None
    kyc_notes: Optional[str] = None

    # Documents (stored as opaque refs; the document service lives in Phase 4)
    document_refs: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 7. KYC Document — uploaded verification evidence (Sprint 3)
# ──────────────────────────────────────────────────────────────────────────────

KycDocType = Literal[
    "passport",
    "tax_id",
    "iban_proof",
    "selfie",
    "source_of_funds",
    "other",
]


class LumenKycDocument(BaseModel):
    """Uploaded KYC evidence. Binary content lives on disk (mock object
    storage); this document holds metadata + the storage path."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    investor_id: str                        # users.user_id
    doc_type: KycDocType = "other"
    filename: str = ""
    content_type: Optional[str] = None
    size_bytes: int = 0
    storage_path: str = ""                  # local path (mock storage, Sprint 3)

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 8. Contracts & Legal Layer (Sprint 4)
# ──────────────────────────────────────────────────────────────────────────────

ContractTemplateKind = Literal[
    "investment_agreement",      # базовий договір інвестування
    "spv_participation",         # договір участі в SPV
    "co_investment",             # договір спільного інвестування
]

ContractStatus = Literal[
    "draft",       # підготовлений, не відправлений
    "generated",   # згенерований із шаблону
    "sent",        # надіслано інвестору на підпис
    "viewed",      # інвестор відкрив договір
    "signed",      # підписано (electronic acceptance)
    "expired",     # строк підписання вийшов
    "cancelled",   # скасовано адміністратором
]


class LumenContractTemplate(BaseModel):
    """Reusable legal template. `body_text` holds UA legal copy with
    {{placeholder}} variables resolved at generation time."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    kind: ContractTemplateKind = "investment_agreement"
    name: str = ""
    body_text: str = ""
    version: int = 1
    active: bool = True

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class LumenContract(BaseModel):
    """Contract instance bound to a specific investment."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    number: str = ""                       # human-readable, e.g. LMN-2026-00012
    investor_id: str
    asset_id: str
    investment_id: str
    template_id: Optional[str] = None
    template_kind: ContractTemplateKind = "investment_agreement"

    status: ContractStatus = "draft"
    title: str = ""
    body_text: str = ""                    # snapshot with placeholders resolved
    version: int = 1                       # template version at generation

    generated_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None

    pdf_url: Optional[str] = None          # /api/contracts/{id}/pdf

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class LumenSignature(BaseModel):
    """Electronic acceptance record (Sprint 4 — not a qualified e-sign)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    contract_id: str
    user_id: str
    status: Literal["signed", "revoked"] = "signed"
    signed_at: datetime = Field(default_factory=_utcnow)
    ip: Optional[str] = None
    user_agent: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 9. Asset Content Platform (Sprint 5) — trust layer around assets
# ──────────────────────────────────────────────────────────────────────────────

AssetUpdateKind = Literal["milestone", "news", "general"]


class LumenAssetUpdate(BaseModel):
    """Project update — the asset's internal blog (milestones, news)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    asset_id: str
    kind: AssetUpdateKind = "general"
    title: str = ""
    body: str = ""
    pinned: bool = False
    published: bool = True
    created_by: Optional[str] = None        # admin users.user_id
    published_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


AssetReportType = Literal["monthly", "quarterly", "annual"]


class LumenAssetReport(BaseModel):
    """Periodic performance report (optionally with an attached file)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    asset_id: str
    report_type: AssetReportType = "quarterly"
    period_label: str = ""                  # e.g. "Q1 2026"
    title: str = ""
    summary: str = ""
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: int = 0
    storage_path: Optional[str] = None      # local mock object storage
    published: bool = True
    created_by: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


AssetDocType = Literal[
    "valuation",        # звіт про оцінку
    "audit",            # аудит
    "lease_agreement",  # договір оренди
    "financial_model",  # фінансова модель
    "permit",           # дозвільна документація
    "legal",            # юридичні документи
    "other",
]

AssetDocVisibility = Literal["public", "investors"]


class LumenAssetDocument(BaseModel):
    """Due-diligence document attached to an asset."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    asset_id: str
    doc_type: AssetDocType = "other"
    title: str = ""
    filename: str = ""
    content_type: Optional[str] = None
    size_bytes: int = 0
    storage_path: str = ""
    visibility: AssetDocVisibility = "public"
    created_by: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


AssetQuestionStatus = Literal["pending", "answered", "hidden"]


class LumenAssetQuestion(BaseModel):
    """Investor Q&A. Answered questions are public to everyone."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    asset_id: str
    investor_id: str
    investor_name: Optional[str] = None
    question: str = ""
    answer: Optional[str] = None
    answered_by: Optional[str] = None
    answered_at: Optional[datetime] = None
    status: AssetQuestionStatus = "pending"

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


SpvStatus = Literal["forming", "active", "dissolved"]


class LumenSpv(BaseModel):
    """Special Purpose Vehicle — the legal wrapper of an asset.

    Asset → SPV → Investors is the future legal backbone; introduced now
    (Sprint 5) so contracts/ownership/reports never need a migration."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=_uuid)
    name: str = ""
    registration_number: Optional[str] = None   # ЄДРПОУ
    jurisdiction: str = "UA"
    asset_id: Optional[str] = None
    status: SpvStatus = "forming"
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# Registry — single source of truth for collection ↔ model mapping
# ──────────────────────────────────────────────────────────────────────────────

LUMEN_COLLECTIONS = {
    "lumen_assets":              LumenAsset,
    "lumen_investment_rounds":   LumenInvestmentRound,
    "lumen_investor_intents":    LumenInvestorIntent,
    "lumen_investments":         LumenInvestment,
    "lumen_ownerships":          LumenOwnership,
    "lumen_investor_profiles":   LumenInvestorProfile,
    "lumen_kyc_documents":       LumenKycDocument,
    "lumen_contract_templates":  LumenContractTemplate,
    "lumen_contracts":           LumenContract,
    "lumen_signatures":          LumenSignature,
    "lumen_asset_updates":       LumenAssetUpdate,
    "lumen_asset_reports":       LumenAssetReport,
    "lumen_asset_documents":     LumenAssetDocument,
    "lumen_asset_questions":     LumenAssetQuestion,
    "lumen_spvs":                LumenSpv,
}

__all__ = [
    "LumenAsset",
    "LumenInvestmentRound",
    "LumenInvestorIntent",
    "LumenInvestment",
    "LumenOwnership",
    "LumenInvestorProfile",
    "LumenKycDocument",
    "LumenContractTemplate",
    "LumenContract",
    "LumenSignature",
    "LumenAssetUpdate",
    "LumenAssetReport",
    "LumenAssetDocument",
    "LumenAssetQuestion",
    "LumenSpv",
    "LUMEN_COLLECTIONS",
]
