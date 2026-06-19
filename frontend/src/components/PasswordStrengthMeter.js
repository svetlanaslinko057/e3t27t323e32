import { useEffect, useMemo, useState } from 'react';
import { Check, X } from 'lucide-react';
import { runtime } from '@/runtime';

/**
 * IR0.6 — Live password strength meter.
 *
 * Mirrors the server-side policy in `backend/lumen_password_policy.py`.
 * The rule descriptor is fetched once from the PUBLIC endpoint
 * `GET /api/auth/password-policy` (so the FE stays in sync with backend),
 * while per-keystroke evaluation happens locally for instant feedback
 * (no network round-trip on every character).
 *
 * The backend remains the source of truth — `/auth/register` and
 * `/auth/password-reset/verify` reject any password that fails the policy.
 */

// Local evaluation mirroring backend rules. Kept deterministic + cheap.
const SPECIALS = "!@#$%^&*()_+-=[]{};:,.?/\\|<>~'\"";
const COMMON = new Set([
  'password', 'password1', 'password!', 'qwerty', 'qwerty123', '12345678',
  'admin', 'admin123', 'welcome', 'welcome1', 'letmein', 'changeme',
  'iloveyou', 'abc12345', 'lumen', 'lumen123', 'investor', 'investor1',
]);

function evaluate(pw, minLen) {
  const v = pw || '';
  const checks = {
    length: v.length >= (minLen || 8) && v.length <= 128,
    lower: /[a-z]/.test(v),
    upper: /[A-Z]/.test(v),
    digit: /[0-9]/.test(v),
    special: [...v].some((c) => SPECIALS.includes(c)),
    no_whitespace: !/\s/.test(v),
    not_common: !COMMON.has(v.toLowerCase()),
  };
  let score = 0;
  if (v.length >= 8) score += 15;
  if (v.length >= 10) score += 10;
  if (v.length >= 12) score += 10;
  if (v.length >= 16) score += 10;
  if (checks.lower) score += 10;
  if (checks.upper) score += 10;
  if (checks.digit) score += 10;
  if (checks.special) score += 15;
  if (checks.no_whitespace) score += 5;
  if (checks.not_common) score += 5;
  score = Math.min(100, score);
  const ok = Object.values(checks).every(Boolean);
  return { checks, score, ok };
}

const RULE_LABELS = {
  length: 'Мінімум 8 символів',
  lower: 'Маленька літера (a–z)',
  upper: 'Велика літера (A–Z)',
  digit: 'Цифра (0–9)',
  special: 'Спеціальний символ (!@#…)',
  no_whitespace: 'Без пробілів',
  not_common: 'Не з простого списку паролів',
};

const RULE_ORDER = ['length', 'lower', 'upper', 'digit', 'special', 'no_whitespace', 'not_common'];

export default function PasswordStrengthMeter({ password = '' }) {
  const [minLen, setMinLen] = useState(8);

  // Fetch the policy descriptor once so labels/min-length track the backend.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await runtime.get('/api/auth/password-policy');
        const policy = res?.data?.policy || res?.policy;
        if (alive && policy?.min_length) setMinLen(policy.min_length);
      } catch (_) {
        /* descriptor is optional — local defaults are fine */
      }
    })();
    return () => { alive = false; };
  }, []);

  const { checks, score, ok } = useMemo(() => evaluate(password, minLen), [password, minLen]);

  if (!password) return null;

  const band = score >= 80 ? { label: 'Надійний', color: '#2E5D4F', bg: '#2E5D4F' }
    : score >= 50 ? { label: 'Середній', color: '#B7791F', bg: '#D69E2E' }
    : { label: 'Слабкий', color: '#C53030', bg: '#E53E3E' };

  return (
    <div className="mt-2 space-y-2" data-testid="password-strength-meter">
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 rounded-full bg-black/10 overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${score}%`, backgroundColor: band.bg }}
            data-testid="password-strength-bar"
          />
        </div>
        <span className="text-xs font-medium" style={{ color: band.color }} data-testid="password-strength-label">
          {band.label}
        </span>
      </div>
      <ul className="grid grid-cols-1 gap-1">
        {RULE_ORDER.map((rule) => {
          const passed = checks[rule];
          return (
            <li
              key={rule}
              className="flex items-center gap-1.5 text-xs"
              style={{ color: passed ? '#2E5D4F' : '#8A8A8A' }}
              data-testid={`pw-rule-${rule}`}
            >
              {passed
                ? <Check className="w-3.5 h-3.5 shrink-0" />
                : <X className="w-3.5 h-3.5 shrink-0 opacity-60" />}
              <span>{RULE_LABELS[rule]}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
