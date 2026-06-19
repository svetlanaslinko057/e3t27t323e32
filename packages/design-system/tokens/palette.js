/**
 * Design System — Master Palette (locked Phase 1, May 2026).
 *
 * CommonJS-compatible JavaScript source so it can be imported by both:
 *   - Web (CRA / craco / webpack) — no TS loader needed.
 *   - Mobile (Expo / Metro / Babel) — `.ts` consumers see types via
 *     `palette.d.ts` alongside.
 *
 * IF YOU EDIT VALUES HERE: you must also edit `palette.css` (CSS variable
 * declarations mirror this 1:1). The audit script `audit/scan_tokens.sh`
 * verifies consistency.
 *
 * Philosophy: one operational OS, rendered in two luminance modes.
 *   - dark  = graphite + sage
 *   - light = warm operational paper + deep sage
 *
 * What changes between dark↔light: substrate, contrast, elevation
 * intensity, atmospheric temperature, signal emphasis. NOTHING else
 * (radius, spacing, typography, density, component anatomy are platform
 * invariants — see `spacing.ts`, `typography/index.ts`).
 *
 * Architectural rules (do not violate):
 *   1. signal ≠ success. Signal = operational gravity (navigation, active,
 *      CTA). Success = a status. They look adjacent but never identical.
 *   2. No marketing/brand expressive colors (emerald, teal, neon mint,
 *      violet, bronze were rejected in design review).
 *   3. Status colors are de-saturated; never neon.
 *   4. Inverse-ink is the text color placed ON TOP of strong fills. Dark
 *      mode = bg color (ink reads as void). Light mode = white.
 */

const DARK = {
  // ===== SUBSTRATE — softened deep ink with warm-cool balance =====
  bg:            '#13151A',
  surface:       '#1B1E26',
  surfaceRaised: '#242833',
  surfaceSunken: '#0E1014',

  // ===== BORDER — slightly stronger to give cards definition =====
  borderSubtle:  'rgba(255,255,255,0.07)',
  borderDefault: 'rgba(255,255,255,0.12)',
  borderStrong:  'rgba(255,255,255,0.20)',

  // ===== TEXT — warm ivory for readability =====
  textPrimary:   '#F0EBDE',
  textSecondary: '#B0AC9F',
  textMuted:     '#7E7B72',
  textInverse:   '#13151A',

  // ===== SIGNAL — operational gravity (calm sage on ink) =====
  signal:        '#8C9B90',
  signalHover:   '#A1B0A5',
  signalActive:  '#7A877E',
  signalInk:     '#13151A',
  signalBgSoft:  'rgba(140,155,144,0.10)',
  signalBgStrong:'rgba(140,155,144,0.20)',
  signalBorder:  'rgba(140,155,144,0.32)',

  // ===== STATUS =====
  success:       '#7E9684',
  successInk:    '#13151A',
  successBgSoft: 'rgba(126,150,132,0.10)',
  successBorder: 'rgba(126,150,132,0.32)',

  warning:       '#C9A961',
  warningInk:    '#13151A',
  warningBgSoft: 'rgba(201,169,97,0.10)',
  warningBorder: 'rgba(201,169,97,0.32)',

  danger:        '#B86A6A',
  dangerInk:     '#13151A',
  dangerBgSoft:  'rgba(184,106,106,0.10)',
  dangerBorder:  'rgba(184,106,106,0.32)',

  info:          '#788491',
  infoInk:       '#13151A',
  infoBgSoft:    'rgba(120,132,145,0.10)',
  infoBorder:    'rgba(120,132,145,0.32)',

  // ===== ELEVATION — softer dark shadows + subtle dawn-gold rim =====
  shadowSm: '0 1px 0 rgba(255,255,255,0.05), 0 4px 14px rgba(0,0,0,0.22)',
  shadowMd: '0 1px 0 rgba(255,255,255,0.06), 0 10px 28px rgba(0,0,0,0.28)',
  shadowLg: '0 1px 0 rgba(255,255,255,0.08), 0 22px 48px rgba(0,0,0,0.38), 0 0 0 1px rgba(212,182,117,0.06)',
};

const LIGHT = {
  // ===== SUBSTRATE — warm operational paper =====
  bg:            '#FAF8F4',
  surface:       '#FFFFFF',
  surfaceRaised: '#F1EEE7',
  surfaceSunken: '#E9E4DA',

  // ===== BORDER =====
  borderSubtle:  'rgba(20,18,15,0.06)',
  borderDefault: 'rgba(20,18,15,0.10)',
  borderStrong:  'rgba(20,18,15,0.16)',

  // ===== TEXT — warm ink =====
  textPrimary:   '#1A1714',
  textSecondary: '#5C544D',
  textMuted:     '#8C8278',
  textInverse:   '#FFFFFF',

  // ===== SIGNAL — deep sage on paper =====
  signal:        '#4A6B5C',
  signalHover:   '#5C7E6E',
  signalActive:  '#3B5749',
  signalInk:     '#FFFFFF',
  signalBgSoft:  'rgba(74,107,92,0.08)',
  signalBgStrong:'rgba(74,107,92,0.14)',
  signalBorder:  'rgba(74,107,92,0.28)',

  // ===== STATUS =====
  success:       '#3E5F4F',
  successInk:    '#FFFFFF',
  successBgSoft: 'rgba(62,95,79,0.08)',
  successBorder: 'rgba(62,95,79,0.24)',

  warning:       '#8A6925',
  warningInk:    '#FFFFFF',
  warningBgSoft: 'rgba(138,105,37,0.08)',
  warningBorder: 'rgba(138,105,37,0.24)',

  danger:        '#8E3E3E',
  dangerInk:     '#FFFFFF',
  dangerBgSoft:  'rgba(142,62,62,0.06)',
  dangerBorder:  'rgba(142,62,62,0.24)',

  info:          '#4B6074',
  infoInk:       '#FFFFFF',
  infoBgSoft:    'rgba(75,96,116,0.06)',
  infoBorder:    'rgba(75,96,116,0.24)',

  // ===== ELEVATION — paper-soft =====
  shadowSm: '0 1px 2px rgba(20,18,15,0.04)',
  shadowMd: '0 1px 2px rgba(20,18,15,0.06), 0 1px 0 rgba(20,18,15,0.04)',
  shadowLg: '0 4px 12px rgba(20,18,15,0.08), 0 1px 0 rgba(20,18,15,0.04)',
};

const palette = { dark: DARK, light: LIGHT };

function getPalette(theme) {
  return theme === 'light' ? LIGHT : DARK;
}

module.exports = { palette, getPalette };
module.exports.palette  = palette;
module.exports.getPalette = getPalette;
// ESM-style named exports for bundlers that detect them:
module.exports.default = palette;
