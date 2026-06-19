/**
 * LanguageContext — Lumen bilingual layer (Українська / English).
 *
 * Ukrainian is the default; English is a first-class, fully switchable locale.
 * The choice is persisted in localStorage and reflected on <html lang>.
 *
 * Three translation surfaces are exposed:
 *   • t(key, fallback)  — dictionary lookup (landing / auth / public site).
 *   • tByEn(enLiteral)  — reverse-map an English literal to the active locale.
 *   • bi(uk, en)        — inline bilingual pair, the lightweight workhorse used
 *                          across the admin / cabinets where strings live in code.
 */
import {
  createContext, useContext, useEffect, useMemo, useCallback, useState,
} from 'react';
import { DICTIONARY, LANGS } from '@/i18n/dictionary';

const STORAGE_KEY = 'lumen_lang';
const DEFAULT_LANG = 'uk';
const SUPPORTED = ['uk', 'en'];

const LanguageContext = createContext({
  lang: DEFAULT_LANG,
  setLang: () => {},
  toggleLang: () => {},
  t: (_k, fallback) => fallback,
  tByEn: (en) => en,
  bi: (uk) => uk,
  languages: LANGS,
});

export { LanguageContext };
export const useLang = () => useContext(LanguageContext);

const norm = (s) => (typeof s === 'string' ? s.trim().replace(/\s+/g, ' ') : s);

const buildReverseIndex = () => {
  const out = {};
  const en = DICTIONARY.en || {};
  for (const [key, val] of Object.entries(en)) {
    if (typeof val === 'string') out[norm(val)] = key;
  }
  return out;
};

const REVERSE_EN = buildReverseIndex();

const readInitialLang = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED.includes(saved)) return saved;
  } catch (_e) { /* noop */ }
  return DEFAULT_LANG;
};

export const LanguageProvider = ({ children }) => {
  const [lang, setLangState] = useState(readInitialLang);

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (_e) { /* noop */ }
    if (typeof document !== 'undefined') {
      document.documentElement.lang = lang;
    }
  }, [lang]);

  const setLang = useCallback((next) => {
    if (SUPPORTED.includes(next)) setLangState(next);
  }, []);

  const toggleLang = useCallback(() => {
    setLangState((cur) => (cur === 'uk' ? 'en' : 'uk'));
  }, []);

  const t = useCallback((key, fallback) => {
    const primary = DICTIONARY[lang] || {};
    if (Object.prototype.hasOwnProperty.call(primary, key)) return primary[key];
    // Fall back to the other locale's dictionary, then to the provided fallback.
    const other = DICTIONARY[lang === 'uk' ? 'en' : 'uk'] || {};
    if (Object.prototype.hasOwnProperty.call(other, key)) return other[key];
    return fallback !== undefined ? fallback : key;
  }, [lang]);

  const tByEn = useCallback((englishLiteral) => {
    if (typeof englishLiteral !== 'string' || !englishLiteral) return englishLiteral;
    if (lang === 'en') return englishLiteral;
    const key = REVERSE_EN[norm(englishLiteral)];
    if (!key) return englishLiteral;
    const dict = DICTIONARY.uk || {};
    return Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : englishLiteral;
  }, [lang]);

  const bi = useCallback((uk, en) => {
    if (lang === 'en') return en !== undefined ? en : uk;
    return uk;
  }, [lang]);

  const value = useMemo(
    () => ({ lang, setLang, toggleLang, t, tByEn, bi, languages: LANGS }),
    [lang, setLang, toggleLang, t, tByEn, bi]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
};

export default LanguageProvider;
