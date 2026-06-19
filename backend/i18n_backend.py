"""
Backend i18n — Accept-Language resolution + lang-aware copy.

Single source of truth for any user-facing string the backend generates:
  • OTP emails (subject + body)
  • Transactional notification copy (title/body)
  • Future: error messages with i18n keys, system-generated activity items

Resolution order for a request's locale:
  1. Explicit `lang` param passed by caller (highest priority)
  2. User record `language` field (persisted via PATCH /account/me from mobile)
  3. `Accept-Language` HTTP header (first matching supported tag)
  4. Default: `en`

Supported languages: `en`, `uk`.

Usage:
  from i18n_backend import resolve_lang, t

  lang = resolve_lang(request=request, user=user_doc)
  subject = t("otp.email.subject", lang, code=code)

Heavy `Accept-Language` parsing is intentionally avoided — we accept a few
common forms (`uk`, `uk-UA`, `en-US,en;q=0.9,uk;q=0.7`) and pick the first
match against {`en`, `uk`}.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("i18n_backend")

SUPPORTED = ("en", "uk")
DEFAULT_LANG = "en"

# ---------------------------------------------------------------- Dictionary
#
# Keys are flat, dotted. Values may contain {placeholder} tokens — formatted
# at lookup time via str.format(**kwargs). Missing placeholders never raise
# (KeyError is caught and the raw template returned).
#
# Add new keys here as new copy surfaces become locale-aware. EN entries
# double as fallback when UK is missing (or vice-versa).

_DICT: dict[str, dict[str, str]] = {
    "en": {
        # --- OTP email -------------------------------------------------------
        "otp.email.subject": "Your EVA-X code is {code}",
        "otp.email.text": "Your EVA-X sign-in code is {code}. It expires in {minutes} minutes.",
        "otp.email.eyebrow": "EVA-X · sign-in",
        "otp.email.headline": "Continue to your product",
        "otp.email.body": "Use this 6-digit code to sign in. It expires in {minutes} minutes.",
        "otp.email.disclaimer": (
            "If you didn't request this code, ignore this email. Someone may have "
            "entered your address by mistake — your account is safe."
        ),
        "otp.email.footer": "EVA-X · Build products. Not tickets.",
        # --- Notifications (transactional, system-generated) -----------------
        "notif.module_assigned.title": "Module assigned to you",
        "notif.module_assigned.body": "You picked up «{module}». Open it to start.",
        "notif.module_shipped.title": "Module shipped",
        "notif.module_shipped.body": "«{module}» passed QA and is now live.",
        "notif.qa_failed.title": "QA returned a module for fixes",
        "notif.qa_failed.body": "«{module}» needs changes — open the feedback notes.",
        "notif.decision_needed.title": "A decision is waiting for you",
        "notif.decision_needed.body": "Project «{project}» — please review and approve.",
        "notif.payout_sent.title": "Payout sent",
        "notif.payout_sent.body": "{amount} {currency} has been released to your method.",
        "notif.payment_received.title": "Payment received",
        "notif.payment_received.body": "{amount} {currency} from {project} settled.",
        "notif.contract_signed.title": "Contract signed",
        "notif.contract_signed.body": "Contract on «{project}» is now binding for both sides.",
        "notif.deliverable_ready.title": "Deliverable ready for review",
        "notif.deliverable_ready.body": "A new build for «{project}» is waiting.",
        "notif.welcome.title": "Welcome aboard!",
        "notif.welcome.body": "Your account is live. Start with the home tour.",
        # --- Referrals / tiers / achievements --------------------------------
        "notif.referral_earned.title": "Referral earned",
        "notif.referral_earned.body": "You earned ${amount} from {referee}'s task.",
        "notif.referral_milestone.title": "Milestone reached!",
        "notif.referral_milestone.body": "{milestone} active referrals — keep going.",
        "notif.tier_up_dev.title": "Tier upgraded to {tier}!",
        "notif.tier_up_dev.body": "Your developer tier is now {tier}. Higher payouts apply.",
        "notif.tier_up_client.title": "You reached {tier} tier!",
        "notif.tier_up_client.body": "You unlocked {tier} perks. Discounts and priority support apply.",
        "notif.dev_joined.title": "New developer joined your tree",
        "notif.dev_joined.body": "{name} joined under your referral. You earn from their work.",
        "notif.achievement_unlocked.title": "Achievement unlocked: {title}",
        "notif.achievement_unlocked.body": "{description} +${amount} bonus",
        # --- Payments / payouts ---------------------------------------------
        "notif.payout.title": "Payout sent — ${amount}",
        "notif.payout.body": "{count} tasks paid via {method}.",
        "notif.payment_received_inv.title": "Payment received — ${amount}",
        "notif.payment_received_inv.body": "{title}",
        "notif.payment_link_resent.title": "Payment link resent",
        "notif.payment_link_resent.body": "{title} — open Billing to pay.",
        # --- Support / revisions --------------------------------------------
        "notif.support_reply.title": "Support replied",
        "notif.support_reply.body": "{preview}",
        "notif.revision_requested.title": "Changes requested: {module}",
        "notif.revision_requested.body": "{feedback}",
        # --- Contracts (legal layer) ----------------------------------------
        "notif.contract_signed_client.title": "Your agreement is signed",
        "notif.contract_signed_client.body": "{project} is fully executed. You're ready to fund it.",
        "notif.contract_signed_admin.title": "Agreement signed",
        "notif.contract_signed_admin.body": "{client} signed the agreement for {project}{price_suffix}.",
        "notif.contract_signed_dev.title": "Project unlocked",
        "notif.contract_signed_dev.body": "{project} has been signed. Awaiting initial payment to start.",
        "notif.contract_reminder.title": "Agreement waiting for your signature",
        "notif.contract_reminder.body": "{project} — please review and sign to start work.",
        # --- Module motion (work units) -------------------------------------
        "notif.module_review.title": "Module ready for QA",
        "notif.module_review.body": "«{module}» — review and accept or reject.",
        "notif.module_done_earn.title": "Module accepted — ${amount}",
        "notif.module_done_earn.body": "«{module}» shipped. Your share is in the next payout.",
        "notif.module_done_ship.title": "Module accepted",
        "notif.module_done_ship.body": "«{module}» shipped successfully.",
        "notif.module_done_client.title": "Module shipped",
        "notif.module_done_client.body": "«{module}» is live in your project.",
        # --- Module motion engine (auto state transitions) ------------------
        "notif.mm.review_required.title": "Review required: {module}",
        "notif.mm.review_required.body": "Approve to ship · dev is waiting",
        "notif.mm.review_ready.title": "Awaiting review: {module}",
        "notif.mm.review_ready.body": "${amount} pending · client is next",
        "notif.mm.review_ready.body_zero": "Client is next · payout on approval",
        "notif.mm.module_done_dev_earn.title": "You earned ${amount}",
        "notif.mm.module_done_dev_earn.body": "{module} completed · paid out",
        "notif.mm.module_done_dev_ship.title": "Module shipped",
        "notif.mm.module_done_dev_ship.body": "{module} completed · paid out",
        "notif.mm.module_done_client.title": "{module} shipped",
        "notif.mm.module_done_client.body": "Your product grew by one module.",
        # --- Project lifecycle ----------------------------------------------
        "notif.contract_signed_live.title": "Contract signed — project is live",
        "notif.contract_signed_live.body": "You started «{project}». Development begins now.",
        "notif.payment_required.title": "Payment required to continue development",
        "notif.payment_required.body": "{title} · ${amount}",
        # --- Errors (HTTPException details) ---------------------------------
        "err.auth.invalid_credentials": "Invalid email or password",
        "err.auth.user_not_found": "User not found",
        "err.auth.account_locked": "Account temporarily locked. Try again later.",
        "err.auth.email_taken": "An account with this email already exists",
        "err.auth.not_authenticated": "Not authenticated",
        "err.auth.invalid_session": "Invalid session",
        "err.auth.session_expired": "Session expired",
        "err.auth.account_blocked": "Account blocked. Contact support.",
        "err.auth.account_deleted": "Account deleted",
        "err.auth.role_required": "You don't have the required role",
        "err.auth.session_id_required": "session_id required",
        "err.auth.password_too_short": "Password must be at least 8 characters",
        "err.auth.invalid_role": "Invalid role",
        "err.auth.invalid_code_format": "Invalid code format",
        "err.otp.invalid": "Invalid or expired code",
        "err.otp.too_many": "Too many attempts. Try again later.",
        "err.otp.no_active_request": "No active reset request. Please request a new code.",
        "err.otp.expired": "Code expired. Please request a new one.",
        "err.otp.too_many_resets": "Too many reset requests. Wait an hour.",
        "err.invoice.not_found": "Invoice not found",
        "err.invoice.already_paid": "Invoice already paid",
        "err.invoice.not_yours": "Not your invoice",
        "err.permission.denied": "You don't have permission to do that",
        "err.access.denied": "Access denied",
        "err.admin.only": "Admin only",
        "err.admin.access_only": "Admin access only",
        "err.client.access_only": "Client access only",
        "err.project.not_found": "Project not found",
        "err.project.not_yours": "Not your project",
        "err.project.no_units": "Project has no work units to save",
        "err.module.not_found": "Module not found",
        "err.module.not_yours": "Not your module",
        "err.module.slug_unknown": "Unknown module slug",
        "err.work_unit.not_found": "Work unit not found",
        "err.work_unit.not_assigned": "Work unit not assigned to you",
        "err.work_unit.not_in_progress": "Unit must be in progress or revision to submit",
        "err.work_unit.not_in_review": "Unit is not in review status",
        "err.task.not_found": "Task not found",
        "err.task.not_yours": "Not your task",
        "err.task.not_assigned": "Not assigned to you",
        "err.task.not_assigned_to_you": "Task not assigned to you",
        "err.task.not_in_revision": "Task is not in revision status",
        "err.request.not_found": "Request not found",
        "err.request.not_distributed": "Request not distributed to you",
        "err.deliverable.not_found": "Deliverable not found",
        "err.deliverable.not_pending": "Deliverable is not pending approval",
        "err.deliverable.url_required": "deliverable_url is required",
        "err.validation_task.not_found": "Validation task not found",
        "err.validation.not_found": "Validation not found",
        "err.withdrawal.not_found": "Withdrawal not found",
        "err.withdrawal.rejected": "Withdrawal was rejected",
        "err.developer.not_found": "Developer not found",
        "err.ticket.not_found": "Ticket not found",
        "err.template.not_found": "Template not found",
        "err.template.name_required": "Template name is required",
        "err.portfolio.not_found": "Portfolio case not found",
        "err.provider.not_found": "Provider not found",
        "err.provider.profile_not_found": "Provider profile not found",
        "err.message.empty": "Empty message",
        "err.contract.not_found": "Contract not found",
        "err.cr.not_found": "CR not found",
        "err.cr.not_yours": "Not your CR",
        "err.lead.not_found": "lead not found",
        "err.lead.already_claimed": "lead already claimed by another user",
        "err.scope.not_found": "Scope not found",
        "err.payout.not_found": "Payout not found",
        "err.inquiry.not_found": "Inquiry not found",
        "err.idea.required": "Idea text is required",
        "err.event.not_found": "Event not found",
        "err.candidate.not_found": "Candidate not found",
        "err.action.not_found": "Action not found",
        "err.action_id.required": "action_id required",
        "err.plan.unknown": "Unknown plan",
        "err.thread.not_found": "Thread not found",
        "err.proposal.not_found": "Proposal not found",
        "err.proposal.not_ready": "Proposal is not ready",
        "err.proposal.not_ready_approval": "Proposal is not ready for approval",
        "err.auth.user_exists": "User already exists",
        "err.auth.not_authorized": "Not authorized",
        "err.auth.invalid_credentials_short": "Invalid credentials",
        "err.auth.terms_required": "You must accept the terms to sign",
        "err.fields.no_editable": "No editable fields provided",
        "err.fields.no_valid": "no valid fields to update",
        "err.mode.invalid_ahd": "mode must be 'ai', 'hybrid' or 'dev'",
        "err.mode.invalid_ma": "mode must be 'manual' or 'auto'",
        "err.context.invalid": "context must be client|developer|admin",
        "err.amount.positive_required": "amount must be positive",
        "err.dev_reward.positive": "dev_reward must be >= 0",
        "err.dev_amount.required": "developer_id and positive amount required",
        "err.kind.invalid": "invalid kind",
        "err.base64.invalid": "invalid base64 payload",
        "err.data_url.invalid": "data_url must be a data: URL",
        "err.rate.out_of_range": "base_hourly_rate must be > 0 and ≤ 5000",
        "err.quick_mode.score": "Quick mode requires behavioral score > 70",
        "err.stripe.not_configured": "stripe_not_configured",
        "err.push.missing_token": 'Missing push token',
        "err.auth.invalid_session_id": 'Invalid session_id',
        "err.reply.empty": 'Empty reply',
        "err.project.cannot_delete_active": 'Cannot delete active project',
        "err.path.invalid": 'Invalid path',
        "err.assignment_mode.invalid": 'Invalid assignment_mode',
        "err.mode.invalid_maa": 'Invalid mode. Must be: manual, assisted, auto',
        "err.decision.invalid": 'Invalid decision. Use: pass, revision, or fail',
        "err.issues.required_for_fail": 'Issues required for fail',
        "err.modules.generate_failed": 'Failed to generate modules',
        "err.approve.before_pay": 'Approve before paying',
        "err.module.cannot_submit": 'Module cannot be submitted in current status',
        "err.module.no_developer": 'Module has no assigned developer',
        "err.module.not_in_review": 'Module must be in review status',
        "err.module.not_available": 'Module not available',
        "err.module.not_reserved": 'Module not reserved',
        "err.module.cannot_drop_completed": 'Cannot drop completed module',
        "err.project.no_deposit": 'No deposit amount on project',
        "err.developers.none_available": 'No developers available',
        "err.developer.no_suitable": 'No suitable developer found',
        "err.timer.not_running": 'No timer running',
        "err.timer.cannot_start": 'Cannot start timer',
        "err.timer.stop_failed": 'Failed to stop timer',
        "err.task.cannot_start": 'Cannot start this task',
        "err.work_unit.cannot_start": 'Cannot start work on this unit',
        "err.cr.not_proposed": 'CR must be in proposed status',
        "err.cr.not_submitted": 'CR must be in submitted status',
        "err.contract.already_signed": 'Contract already signed — plan locked',
        "err.contract.not_yours": 'Not your contract',
        "err.deliverable.no_price": 'Deliverable has no price set',
        "err.capacity.max": 'Maximum capacity reached (2 modules)',
        "err.fields.no_update": 'No fields to update',
        "err.invoice.not_found_for_deliverable": 'No invoice found for this deliverable',
        "err.referral.dev_only": 'Only developers/testers can be referred in dev growth program',
        "err.action.already_done": 'Action already executed or failed',
        "err.otp.invalid_code": 'Invalid code',
        "err.otp.too_many_requests": 'Too many attempts. Request a new code.',
        "err.auth.not_authorized_time_logs": "Not authorized to view this task's time logs",
        "err.alert.not_found": 'Alert not found',
        "err.batch.not_found": 'Batch not found',
        "err.contract.not_found_for_project": 'No contract for this project',
        "err.milestone.none_ready": 'No milestone is ready to continue.',
        "err.divergence.none_open": 'No open divergence with that id',
        "err.notification.not_found": 'Notification not found',
        "err.project.not_found_or_not_yours": 'Project not found or not yours',
        "err.ai.invalid_format": 'AI returned invalid format. Please try again.',
        "err.ai.not_configured": 'AI service not configured — admin must set an LLM key in /admin/integrations',
        "err.ai.parse_failed": 'Failed to parse AI response',
        "err.idea.process_failed": 'Failed to process idea',
        "err.llm.not_configured": 'LLM key not configured — admin must set one in /admin/integrations',
        "err.sort.invalid": 'Invalid sort_by parameter',
        "err.period.invalid": "Period must be 'today', 'week', or 'month'",
        "err.auth.not_authorized_qa": "Not authorized to view this task's QA history",
        "err.generic.bad_request": "Bad request",
        "err.generic.not_found": "Not found",
        "err.generic.server_error": "Something went wrong. Please try again.",

        # --- Generic state-machine / validation errors (Phase i18n closeout) -
        "err.invalid_status_transition":  "Cannot {action} from status: {status}",
        "err.invalid_status_for_action":  "Cannot {action} in status: {status}",
        "err.invalid_status_choice":      "Invalid status. Must be one of: {allowed}",
        "err.invalid_priority_choice":    "Invalid priority. Must be one of: {allowed}",
        "err.invoice.not_payable":        "Invoice status '{status}' is not payable",
        "err.invoice.cannot_pay":         "Cannot pay (status={status})",
        "err.plan.must_be_one_of":        "plan must be one of {plans}",
        "err.batch.already_status":       "Batch already {status}",
        "err.candidate.already_reviewed": "Candidate already reviewed ({status})",
        "err.action.not_executable":      "Action not executable. Status: {status}",
        "err.unit.cannot_submit":         "Cannot submit from status: {status}",
        "err.deliverable.not_ready":      "Deliverable not ready for payment. Status: {status}",
        "err.deliverable.not_payable":    "Deliverable not payable (status: {status})",
        "err.task.not_acceptable":        "Task cannot be accepted (status: {status})",
        "err.decline_reason.invalid":     "Invalid decline reason. Must be one of: {allowed}",
        "err.payout.cannot_approve":      "Cannot approve payout in status: {status}",
        "err.status.cannot_transition":   "Cannot transition from {current} to {target}",
    },
    "uk": {
        # --- OTP email -------------------------------------------------------
        "otp.email.subject": "Ваш код EVA-X: {code}",
        "otp.email.text": "Ваш код входу в EVA-X: {code}. Він діє {minutes} хв.",
        "otp.email.eyebrow": "EVA-X · вхід",
        "otp.email.headline": "Продовжуйте до вашого продукту",
        "otp.email.body": "Використайте цей 6-значний код для входу. Він діє {minutes} хв.",
        "otp.email.disclaimer": (
            "Якщо ви не запитували цей код — просто проігноруйте лист. "
            "Можливо, хтось випадково вказав вашу адресу — ваш акаунт у безпеці."
        ),
        "otp.email.footer": "EVA-X · Створюйте продукти. Не тікети.",
        # --- Notifications ---------------------------------------------------
        "notif.module_assigned.title": "Вам призначено модуль",
        "notif.module_assigned.body": "Ви взяли в роботу «{module}». Відкрийте, щоб почати.",
        "notif.module_shipped.title": "Модуль здано",
        "notif.module_shipped.body": "«{module}» пройшов QA і вже в продакшні.",
        "notif.qa_failed.title": "QA повернуло модуль на доопрацювання",
        "notif.qa_failed.body": "«{module}» потребує правок — перегляньте коментарі.",
        "notif.decision_needed.title": "Чекає ваше рішення",
        "notif.decision_needed.body": "Проєкт «{project}» — перегляньте та підтвердьте.",
        "notif.payout_sent.title": "Виплату надіслано",
        "notif.payout_sent.body": "{amount} {currency} переказано на ваш спосіб виплат.",
        "notif.payment_received.title": "Платіж отримано",
        "notif.payment_received.body": "{amount} {currency} від {project} зараховано.",
        "notif.contract_signed.title": "Контракт підписано",
        "notif.contract_signed.body": "Контракт по «{project}» тепер обов'язковий для обох сторін.",
        "notif.deliverable_ready.title": "Поставка готова до огляду",
        "notif.deliverable_ready.body": "Нова збірка по «{project}» чекає на вас.",
        "notif.welcome.title": "Ласкаво просимо!",
        "notif.welcome.body": "Ваш акаунт активний. Почніть з туру по головній.",
        # --- Referrals / tiers / achievements --------------------------------
        "notif.referral_earned.title": "Реферальний бонус",
        "notif.referral_earned.body": "Ви отримали ${amount} з задачі {referee}.",
        "notif.referral_milestone.title": "Досягнуто рубіж!",
        "notif.referral_milestone.body": "{milestone} активних рефералів — продовжуйте.",
        "notif.tier_up_dev.title": "Підвищення до рівня {tier}!",
        "notif.tier_up_dev.body": "Ваш рівень розробника тепер {tier}. Виплати тепер вищі.",
        "notif.tier_up_client.title": "Ви досягли рівня {tier}!",
        "notif.tier_up_client.body": "Розблоковано переваги {tier}: знижки та пріоритетна підтримка.",
        "notif.dev_joined.title": "Новий розробник у вашому дереві",
        "notif.dev_joined.body": "{name} приєднався за вашим реферальним кодом. Ви отримуєте з його роботи.",
        "notif.achievement_unlocked.title": "Досягнення відкрито: {title}",
        "notif.achievement_unlocked.body": "{description} +${amount} бонус",
        # --- Payments / payouts ---------------------------------------------
        "notif.payout.title": "Виплату надіслано — ${amount}",
        "notif.payout.body": "Оплачено {count} задач через {method}.",
        "notif.payment_received_inv.title": "Платіж отримано — ${amount}",
        "notif.payment_received_inv.body": "{title}",
        "notif.payment_link_resent.title": "Посилання на оплату повторно надіслано",
        "notif.payment_link_resent.body": "{title} — відкрийте Білінг для оплати.",
        # --- Support / revisions --------------------------------------------
        "notif.support_reply.title": "Відповідь підтримки",
        "notif.support_reply.body": "{preview}",
        "notif.revision_requested.title": "Запит на правки: {module}",
        "notif.revision_requested.body": "{feedback}",
        # --- Contracts (legal layer) ----------------------------------------
        "notif.contract_signed_client.title": "Ваш договір підписано",
        "notif.contract_signed_client.body": "{project} повністю погоджено. Можна фінансувати запуск.",
        "notif.contract_signed_admin.title": "Договір підписано",
        "notif.contract_signed_admin.body": "{client} підписав(-ла) договір по {project}{price_suffix}.",
        "notif.contract_signed_dev.title": "Проєкт розблоковано",
        "notif.contract_signed_dev.body": "{project} підписано. Очікуємо першого платежу для старту.",
        "notif.contract_reminder.title": "Договір чекає вашого підпису",
        "notif.contract_reminder.body": "{project} — будь ласка, перегляньте та підпишіть для старту.",
        # --- Module motion --------------------------------------------------
        "notif.module_review.title": "Модуль готовий до QA",
        "notif.module_review.body": "«{module}» — перегляньте та прийміть або відхиліть.",
        "notif.module_done_earn.title": "Модуль прийнято — ${amount}",
        "notif.module_done_earn.body": "«{module}» здано. Ваша частка — у наступній виплаті.",
        "notif.module_done_ship.title": "Модуль прийнято",
        "notif.module_done_ship.body": "«{module}» успішно здано.",
        "notif.module_done_client.title": "Модуль здано",
        "notif.module_done_client.body": "«{module}» доступний у вашому проєкті.",
        # --- Module motion engine (auto state transitions) ------------------
        "notif.mm.review_required.title": "Потрібен огляд: {module}",
        "notif.mm.review_required.body": "Підтвердьте, щоб відправити · розробник чекає",
        "notif.mm.review_ready.title": "Очікує огляду: {module}",
        "notif.mm.review_ready.body": "${amount} в очікуванні · черга клієнта",
        "notif.mm.review_ready.body_zero": "Черга клієнта · виплата після підтвердження",
        "notif.mm.module_done_dev_earn.title": "Ви заробили ${amount}",
        "notif.mm.module_done_dev_earn.body": "{module} завершено · виплачено",
        "notif.mm.module_done_dev_ship.title": "Модуль здано",
        "notif.mm.module_done_dev_ship.body": "{module} завершено · виплачено",
        "notif.mm.module_done_client.title": "{module} здано",
        "notif.mm.module_done_client.body": "Ваш продукт виріс ще на один модуль.",
        # --- Project lifecycle ----------------------------------------------
        "notif.contract_signed_live.title": "Договір підписано — проєкт активний",
        "notif.contract_signed_live.body": "Ви запустили «{project}». Розробка починається зараз.",
        "notif.payment_required.title": "Потрібна оплата для продовження розробки",
        "notif.payment_required.body": "{title} · ${amount}",
        # --- Errors ---------------------------------------------------------
        "err.auth.invalid_credentials": "Невірний email або пароль",
        "err.auth.user_not_found": "Користувача не знайдено",
        "err.auth.account_locked": "Акаунт тимчасово заблоковано. Спробуйте пізніше.",
        "err.auth.email_taken": "Акаунт з таким email вже існує",
        "err.auth.not_authenticated": "Не авторизовано",
        "err.auth.invalid_session": "Невірна сесія",
        "err.auth.session_expired": "Сесія завершена",
        "err.auth.account_blocked": "Акаунт заблоковано. Зверніться до підтримки.",
        "err.auth.account_deleted": "Акаунт видалено",
        "err.auth.role_required": "Бракує потрібної ролі для цієї дії",
        "err.auth.session_id_required": "Потрібен session_id",
        "err.auth.password_too_short": "Пароль має містити щонайменше 8 символів",
        "err.auth.invalid_role": "Невірна роль",
        "err.auth.invalid_code_format": "Невірний формат коду",
        "err.otp.invalid": "Невірний або прострочений код",
        "err.otp.too_many": "Забагато спроб. Спробуйте пізніше.",
        "err.otp.no_active_request": "Немає активного запиту на скидання. Запросіть новий код.",
        "err.otp.expired": "Код прострочено. Запросіть новий.",
        "err.otp.too_many_resets": "Забагато запитів на скидання. Зачекайте годину.",
        "err.invoice.not_found": "Інвойс не знайдено",
        "err.invoice.already_paid": "Інвойс вже оплачено",
        "err.invoice.not_yours": "Це не ваш інвойс",
        "err.permission.denied": "У вас немає прав на цю дію",
        "err.access.denied": "Доступ заборонено",
        "err.admin.only": "Лише для адміністратора",
        "err.admin.access_only": "Доступ лише для адміністратора",
        "err.client.access_only": "Доступ лише для клієнта",
        "err.project.not_found": "Проєкт не знайдено",
        "err.project.not_yours": "Це не ваш проєкт",
        "err.project.no_units": "Проєкт не має робочих юнітів для збереження",
        "err.module.not_found": "Модуль не знайдено",
        "err.module.not_yours": "Це не ваш модуль",
        "err.module.slug_unknown": "Невідомий slug модуля",
        "err.work_unit.not_found": "Робочий юніт не знайдено",
        "err.work_unit.not_assigned": "Робочий юніт не призначено вам",
        "err.work_unit.not_in_progress": "Юніт має бути в роботі або на ревізії, щоб надіслати",
        "err.work_unit.not_in_review": "Юніт не у статусі ревʼю",
        "err.task.not_found": "Задачу не знайдено",
        "err.task.not_yours": "Це не ваша задача",
        "err.task.not_assigned": "Не призначено вам",
        "err.task.not_assigned_to_you": "Задачу не призначено вам",
        "err.task.not_in_revision": "Задача не в статусі ревізії",
        "err.request.not_found": "Запит не знайдено",
        "err.request.not_distributed": "Запит не розподілено вам",
        "err.deliverable.not_found": "Поставку не знайдено",
        "err.deliverable.not_pending": "Поставка не на схваленні",
        "err.deliverable.url_required": "Потрібно deliverable_url",
        "err.validation_task.not_found": "Завдання валідації не знайдено",
        "err.validation.not_found": "Валідацію не знайдено",
        "err.withdrawal.not_found": "Виведення не знайдено",
        "err.withdrawal.rejected": "Виведення відхилено",
        "err.developer.not_found": "Розробника не знайдено",
        "err.ticket.not_found": "Тікет не знайдено",
        "err.template.not_found": "Шаблон не знайдено",
        "err.template.name_required": "Потрібна назва шаблону",
        "err.portfolio.not_found": "Кейс портфоліо не знайдено",
        "err.provider.not_found": "Провайдера не знайдено",
        "err.provider.profile_not_found": "Профіль провайдера не знайдено",
        "err.message.empty": "Порожнє повідомлення",
        "err.contract.not_found": "Контракт не знайдено",
        "err.cr.not_found": "CR не знайдено",
        "err.cr.not_yours": "Це не ваш CR",
        "err.lead.not_found": "Лід не знайдено",
        "err.lead.already_claimed": "Лід вже взятий іншим користувачем",
        "err.scope.not_found": "Скоуп не знайдено",
        "err.payout.not_found": "Виплату не знайдено",
        "err.inquiry.not_found": "Запит не знайдено",
        "err.idea.required": "Потрібен текст ідеї",
        "err.event.not_found": "Подію не знайдено",
        "err.candidate.not_found": "Кандидата не знайдено",
        "err.action.not_found": "Дію не знайдено",
        "err.action_id.required": "Потрібен action_id",
        "err.plan.unknown": "Невідомий план",
        "err.thread.not_found": "Тред не знайдено",
        "err.proposal.not_found": "Пропозицію не знайдено",
        "err.proposal.not_ready": "Пропозиція не готова",
        "err.proposal.not_ready_approval": "Пропозиція не готова до схвалення",
        "err.auth.user_exists": "Користувач уже існує",
        "err.auth.not_authorized": "Не авторизовано",
        "err.auth.invalid_credentials_short": "Невірні дані",
        "err.auth.terms_required": "Потрібно прийняти умови",
        "err.fields.no_editable": "Не надано полів для редагування",
        "err.fields.no_valid": "Немає валідних полів для оновлення",
        "err.mode.invalid_ahd": "mode має бути 'ai', 'hybrid' або 'dev'",
        "err.mode.invalid_ma": "mode має бути 'manual' або 'auto'",
        "err.context.invalid": "context має бути client|developer|admin",
        "err.amount.positive_required": "Сума має бути додатньою",
        "err.dev_reward.positive": "dev_reward має бути >= 0",
        "err.dev_amount.required": "Потрібен developer_id та додатня сума",
        "err.kind.invalid": "Невірний kind",
        "err.base64.invalid": "Невірний base64 payload",
        "err.data_url.invalid": "data_url має бути data: URL",
        "err.rate.out_of_range": "base_hourly_rate має бути > 0 та ≤ 5000",
        "err.quick_mode.score": "Швидкий режим вимагає behavioral score > 70",
        "err.stripe.not_configured": "Stripe не налаштовано",
        "err.push.missing_token": 'Відсутній push-токен',
        "err.auth.invalid_session_id": 'Невірний session_id',
        "err.reply.empty": 'Порожня відповідь',
        "err.project.cannot_delete_active": 'Не можна видалити активний проєкт',
        "err.path.invalid": 'Невірний шлях',
        "err.assignment_mode.invalid": 'Невірний assignment_mode',
        "err.mode.invalid_maa": 'Невірний режим. Має бути: manual, assisted, auto',
        "err.decision.invalid": 'Невірне рішення. Використовуйте: pass, revision або fail',
        "err.issues.required_for_fail": 'Для fail потрібно вказати issues',
        "err.modules.generate_failed": 'Не вдалося згенерувати модулі',
        "err.approve.before_pay": 'Підтвердіть перед оплатою',
        "err.module.cannot_submit": 'Модуль не можна надіслати в поточному статусі',
        "err.module.no_developer": 'Модулю не призначено розробника',
        "err.module.not_in_review": 'Модуль має бути в статусі ревʼю',
        "err.module.not_available": 'Модуль недоступний',
        "err.module.not_reserved": 'Модуль не заброньовано',
        "err.module.cannot_drop_completed": 'Не можна скасувати завершений модуль',
        "err.project.no_deposit": 'На проєкті немає суми депозиту',
        "err.developers.none_available": 'Немає доступних розробників',
        "err.developer.no_suitable": 'Підходящого розробника не знайдено',
        "err.timer.not_running": 'Таймер не запущено',
        "err.timer.cannot_start": 'Не вдалося запустити таймер',
        "err.timer.stop_failed": 'Не вдалося зупинити таймер',
        "err.task.cannot_start": 'Неможливо розпочати цю задачу',
        "err.work_unit.cannot_start": 'Неможливо почати роботу над цим юнітом',
        "err.cr.not_proposed": 'CR має бути в статусі proposed',
        "err.cr.not_submitted": 'CR має бути в статусі submitted',
        "err.contract.already_signed": 'Контракт вже підписано — план зафіксовано',
        "err.contract.not_yours": 'Це не ваш контракт',
        "err.deliverable.no_price": 'Поставці не задано ціну',
        "err.capacity.max": 'Досягнуто максимуму (2 модулі)',
        "err.fields.no_update": 'Немає полів для оновлення',
        "err.invoice.not_found_for_deliverable": 'Інвойс для цієї поставки не знайдено',
        "err.referral.dev_only": 'У програмі росту можуть бути лише розробники/тестувальники',
        "err.action.already_done": 'Дія вже виконана або завершилася помилкою',
        "err.otp.invalid_code": 'Невірний код',
        "err.otp.too_many_requests": 'Забагато спроб. Запросіть новий код.',
        "err.auth.not_authorized_time_logs": 'Немає прав на перегляд time logs цієї задачі',
        "err.alert.not_found": 'Алерт не знайдено',
        "err.batch.not_found": 'Батч не знайдено',
        "err.contract.not_found_for_project": 'Для цього проєкту немає контракту',
        "err.milestone.none_ready": 'Немає готового milestone для продовження.',
        "err.divergence.none_open": 'Немає відкритої розбіжності з таким id',
        "err.notification.not_found": 'Сповіщення не знайдено',
        "err.project.not_found_or_not_yours": 'Проєкт не знайдено або він не ваш',
        "err.ai.invalid_format": 'AI повернув невірний формат. Спробуйте ще раз.',
        "err.ai.not_configured": 'AI-сервіс не налаштовано — адміністратор має додати LLM-ключ у /admin/integrations',
        "err.ai.parse_failed": 'Не вдалося розпарсити відповідь AI',
        "err.idea.process_failed": 'Не вдалося обробити ідею',
        "err.llm.not_configured": 'LLM-ключ не налаштовано — адміністратор має задати його у /admin/integrations',
        "err.sort.invalid": 'Невірний параметр sort_by',
        "err.period.invalid": "Період має бути 'today', 'week' або 'month'",
        "err.auth.not_authorized_qa": 'Немає прав на перегляд історії QA цієї задачі',
        "err.push.missing_token": 'Відсутній push-токен',
        "err.auth.invalid_session_id": 'Невірний session_id',
        "err.reply.empty": 'Порожня відповідь',
        "err.project.cannot_delete_active": 'Не можна видалити активний проєкт',
        "err.path.invalid": 'Невірний шлях',
        "err.assignment_mode.invalid": 'Невірний assignment_mode',
        "err.mode.invalid_maa": 'Невірний режим. Має бути: manual, assisted, auto',
        "err.decision.invalid": 'Невірне рішення. Використовуйте: pass, revision або fail',
        "err.issues.required_for_fail": 'Для fail потрібно вказати issues',
        "err.modules.generate_failed": 'Не вдалося згенерувати модулі',
        "err.approve.before_pay": 'Підтвердіть перед оплатою',
        "err.module.cannot_submit": 'Модуль не можна надіслати в поточному статусі',
        "err.module.no_developer": 'Модулю не призначено розробника',
        "err.module.not_in_review": 'Модуль має бути в статусі ревʼю',
        "err.module.not_available": 'Модуль недоступний',
        "err.module.not_reserved": 'Модуль не заброньовано',
        "err.module.cannot_drop_completed": 'Не можна скасувати завершений модуль',
        "err.project.no_deposit": 'На проєкті немає суми депозиту',
        "err.developers.none_available": 'Немає доступних розробників',
        "err.developer.no_suitable": 'Підходящого розробника не знайдено',
        "err.timer.not_running": 'Таймер не запущено',
        "err.timer.cannot_start": 'Не вдалося запустити таймер',
        "err.timer.stop_failed": 'Не вдалося зупинити таймер',
        "err.task.cannot_start": 'Неможливо розпочати цю задачу',
        "err.work_unit.cannot_start": 'Неможливо почати роботу над цим юнітом',
        "err.cr.not_proposed": 'CR має бути в статусі proposed',
        "err.cr.not_submitted": 'CR має бути в статусі submitted',
        "err.contract.already_signed": 'Контракт вже підписано — план зафіксовано',
        "err.contract.not_yours": 'Це не ваш контракт',
        "err.deliverable.no_price": 'Поставці не задано ціну',
        "err.capacity.max": 'Досягнуто максимуму (2 модулі)',
        "err.fields.no_update": 'Немає полів для оновлення',
        "err.invoice.not_found_for_deliverable": 'Інвойс для цієї поставки не знайдено',
        "err.referral.dev_only": 'У програмі росту можуть бути лише розробники/тестувальники',
        "err.action.already_done": 'Дія вже виконана або завершилася помилкою',
        "err.otp.invalid_code": 'Невірний код',
        "err.otp.too_many_requests": 'Забагато спроб. Запросіть новий код.',
        "err.auth.not_authorized_time_logs": 'Немає прав на перегляд time logs цієї задачі',
        "err.alert.not_found": 'Алерт не знайдено',
        "err.batch.not_found": 'Батч не знайдено',
        "err.contract.not_found_for_project": 'Для цього проєкту немає контракту',
        "err.milestone.none_ready": 'Немає готового milestone для продовження.',
        "err.divergence.none_open": 'Немає відкритої розбіжності з таким id',
        "err.notification.not_found": 'Сповіщення не знайдено',
        "err.project.not_found_or_not_yours": 'Проєкт не знайдено або він не ваш',
        "err.ai.invalid_format": 'AI повернув невірний формат. Спробуйте ще раз.',
        "err.ai.not_configured": 'AI-сервіс не налаштовано — адміністратор має додати LLM-ключ у /admin/integrations',
        "err.ai.parse_failed": 'Не вдалося розпарсити відповідь AI',
        "err.idea.process_failed": 'Не вдалося обробити ідею',
        "err.llm.not_configured": 'LLM-ключ не налаштовано — адміністратор має задати його у /admin/integrations',
        "err.generic.bad_request": "Невірний запит",
        "err.generic.not_found": "Не знайдено",
        "err.generic.server_error": "Щось пішло не так. Спробуйте ще раз.",

        # --- Generic state-machine / validation errors (Phase i18n closeout) -
        "err.invalid_status_transition":  "Неможливо {action} зі стану: {status}",
        "err.invalid_status_for_action":  "Неможливо {action} у стані: {status}",
        "err.invalid_status_choice":      "Невірний стан. Має бути один з: {allowed}",
        "err.invalid_priority_choice":    "Невірний пріоритет. Має бути один з: {allowed}",
        "err.invoice.not_payable":        "Інвойс у стані «{status}» не підлягає оплаті",
        "err.invoice.cannot_pay":         "Не можна оплатити (стан={status})",
        "err.plan.must_be_one_of":        "plan має бути один з {plans}",
        "err.batch.already_status":       "Батч уже {status}",
        "err.candidate.already_reviewed": "Кандидата вже оцінено ({status})",
        "err.action.not_executable":      "Дія недоступна для виконання. Стан: {status}",
        "err.unit.cannot_submit":         "Не можна подати зі стану: {status}",
        "err.deliverable.not_ready":      "Поставка не готова до оплати. Стан: {status}",
        "err.deliverable.not_payable":    "Поставка не підлягає оплаті (стан: {status})",
        "err.task.not_acceptable":        "Завдання не можна прийняти (стан: {status})",
        "err.decline_reason.invalid":     "Невірна причина відмови. Має бути одна з: {allowed}",
        "err.payout.cannot_approve":      "Не можна схвалити виплату у стані: {status}",
        "err.status.cannot_transition":   "Неможливий перехід зі стану {current} у {target}",
    },
}


# ---------------------------------------------------------------- Helpers
def _parse_accept_language(header: str) -> list[str]:
    """Return ordered list of language tags from an Accept-Language header.

    Example: `en-US,en;q=0.9,uk;q=0.7` → ['en-us', 'en', 'uk'].
    Quality values are honoured only via their natural order in the header
    (browsers already emit highest-q first); we don't sort by `q` value.
    """
    if not header:
        return []
    out: list[str] = []
    for part in header.split(","):
        tag = part.split(";", 1)[0].strip().lower()
        if tag and tag not in out:
            out.append(tag)
    return out


def _match_supported(tags: list[str]) -> Optional[str]:
    """Pick the first tag that matches a supported language (with base-fallback)."""
    for tag in tags:
        base = tag.split("-", 1)[0]
        if base in SUPPORTED:
            return base
    return None


def resolve_lang(
    request: Any = None,
    user: Optional[dict] = None,
    explicit: Optional[str] = None,
) -> str:
    """Resolve the request's effective language. See module docstring.

    `request` may be a Starlette/FastAPI Request, or anything with a `.headers`
    dict-like attribute. Failures are swallowed — we always return one of
    SUPPORTED.
    """
    # 1. Explicit
    if explicit:
        e = explicit.strip().lower().split("-", 1)[0]
        if e in SUPPORTED:
            return e

    # 2. User preference
    if user:
        lang = (user.get("language") or "").strip().lower().split("-", 1)[0]
        if lang in SUPPORTED:
            return lang

    # 3. Accept-Language header
    if request is not None:
        try:
            header = request.headers.get("accept-language") or request.headers.get(
                "Accept-Language"
            ) or ""
        except Exception:
            header = ""
        match = _match_supported(_parse_accept_language(header))
        if match:
            return match

    return DEFAULT_LANG


def t(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """Translate `key` into `lang`, formatting any {placeholders} with kwargs.

    Falls back to English, then to the key itself if both are missing.
    Format errors return the raw template untouched.
    """
    lang = (lang or DEFAULT_LANG).strip().lower()
    if lang not in SUPPORTED:
        lang = DEFAULT_LANG
    template = _DICT.get(lang, {}).get(key) or _DICT[DEFAULT_LANG].get(key) or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError) as e:
        logger.debug("i18n format failed for key=%s lang=%s: %s", key, lang, e)
        return template


# Public surface
__all__ = ["resolve_lang", "t", "raise_http", "SUPPORTED", "DEFAULT_LANG"]


def raise_http(
    status_code: int,
    key: str,
    request: Any = None,
    user: Optional[dict] = None,
    explicit_lang: Optional[str] = None,
    **fmt: Any,
):
    """Raise an HTTPException with a localized `detail`.

    Optional integration point for translating user-facing API errors.
    Falls back to the English message (or the bare key) if the key
    isn't registered. Safe to use from any route handler:

        from i18n_backend import raise_http
        raise_http(401, "err.auth.invalid_credentials", request=request)

    The helper resolves language via `resolve_lang(request, user, explicit_lang)`
    so it works whether the user is authenticated or anonymous.
    """
    # Imported lazily to keep this module free of FastAPI coupling at import.
    from fastapi import HTTPException

    lang = resolve_lang(request=request, user=user, explicit=explicit_lang)
    detail = t(key, lang, **fmt)
    raise HTTPException(status_code=status_code, detail=detail)
