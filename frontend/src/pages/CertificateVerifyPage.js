/**
 * CertificateVerifyPage — LUMEN 2.0 / Phase A2.
 * PUBLIC certificate verification (no auth, no private investor data).
 * Reachable at /certificates/verify/:code (and /certificates/verify for manual entry).
 */
import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ShieldCheck, ShieldAlert, Search, Loader2, Building2, Boxes, PieChart, Calendar,
} from 'lucide-react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const nfmt = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 0 });

const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('uk-UA', { day: '2-digit', month: 'long', year: 'numeric' }); }
  catch { return '—'; }
};

export default function CertificateVerifyPage() {
  const { code: routeCode } = useParams();
  const navigate = useNavigate();
  const [code, setCode] = useState(routeCode || '');
  const [state, setState] = useState('idle'); // idle | loading | ok | invalid | error
  const [cert, setCert] = useState(null);

  const verify = useCallback(async (c) => {
    if (!c) return;
    setState('loading');
    try {
      const r = await axios.get(`${API}/public/certificates/verify/${encodeURIComponent(c)}`);
      setCert(r.data);
      setState('ok');
    } catch (e) {
      if (e?.response?.status === 404) { setState('invalid'); setCert(null); }
      else { setState('error'); }
    }
  }, []);

  useEffect(() => { if (routeCode) verify(routeCode); }, [routeCode, verify]);

  const onSubmit = (e) => {
    e.preventDefault();
    if (code) navigate(`/certificates/verify/${encodeURIComponent(code.trim())}`);
  };

  const valid = cert?.valid;

  return (
    <div className="min-h-screen bg-app text-token-primary flex flex-col items-center px-4 py-10" data-testid="certificate-verify">
      <Link to="/" className="mb-8 flex items-center gap-2" data-testid="verify-logo">
        <span className="text-2xl font-extrabold tracking-tight" style={{ color: '#2E5D4F' }}>LUMEN</span>
      </Link>

      <div className="w-full max-w-lg">
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2 text-token-kicker"><ShieldCheck className="w-4 h-4" /> Перевірка сертифіката</div>
          <h1 className="text-2xl font-bold mt-2">Верифікація інвестиційного сертифіката</h1>
          <p className="text-small-token mt-1">Введіть код сертифіката, щоб перевірити його дійсність у реєстрі LUMEN.</p>
        </div>

        <form onSubmit={onSubmit} className="flex items-center gap-2 mb-6">
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="XXXX-XXXX-XXXX" data-testid="verify-input"
            className="flex-1 px-4 py-3 rounded-xl border border-app bg-app-surface text-token-primary outline-none focus:border-app-strong tracking-widest font-mono" />
          <button type="submit" data-testid="verify-submit"
            className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-[#2E5D4F] text-white font-semibold hover:bg-[#274f43] transition">
            <Search className="w-4 h-4" /> Перевірити
          </button>
        </form>

        {state === 'loading' && (
          <div className="rounded-2xl border border-app bg-app-surface p-10 text-center" data-testid="verify-loading">
            <Loader2 className="w-8 h-8 mx-auto animate-spin text-token-muted" />
            <p className="text-sm text-token-muted mt-3">Перевіряємо…</p>
          </div>
        )}

        {state === 'invalid' && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/5 p-8 text-center" data-testid="verify-invalid">
            <ShieldAlert className="w-10 h-10 mx-auto text-rose-500 mb-3" />
            <p className="font-semibold text-rose-600">Сертифікат не знайдено</p>
            <p className="text-sm text-token-muted mt-1">Код недійсний або сертифікат не існує в реєстрі.</p>
          </div>
        )}

        {state === 'error' && (
          <div className="rounded-2xl border border-app bg-app-surface p-8 text-center" data-testid="verify-error">
            <p className="text-sm text-token-muted">Сталася помилка. Спробуйте ще раз.</p>
          </div>
        )}

        {state === 'ok' && cert && (
          <div className="rounded-2xl border border-app bg-app-surface overflow-hidden" data-testid="verify-result">
            <div className={`p-5 flex items-center gap-3 ${valid ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}>
              {valid ? <ShieldCheck className="w-8 h-8 text-emerald-500" /> : <ShieldAlert className="w-8 h-8 text-rose-500" />}
              <div>
                <div className={`font-bold ${valid ? 'text-emerald-600' : 'text-rose-600'}`} data-testid="verify-status">
                  {valid ? 'Сертифікат дійсний' : `Сертифікат недійсний (${cert.status})`}
                </div>
                <div className="text-sm text-token-muted">{cert.certificate_number}</div>
              </div>
            </div>
            <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field icon={Building2} label="Актив" value={cert.asset_title} />
              <Field icon={Building2} label="SPV" value={cert.spv_name} />
              <Field icon={Boxes} label="Одиниці" value={nfmt(cert.units)} />
              <Field icon={PieChart} label="Частка" value={`${Number(cert.ownership_percent).toFixed(4)} %`} />
              <Field icon={Calendar} label="Дата випуску" value={fmtDate(cert.issue_date)} />
              <Field icon={ShieldCheck} label="Код" value={cert.verify_code} />
            </div>
            <div className="px-5 py-3 border-t border-app text-[11px] text-token-muted">
              Джерело істини: LUMEN Unit Registry. Персональні дані власника не розкриваються.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ icon: Icon, label, value }) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-9 h-9 rounded-lg bg-app-elevated flex items-center justify-center shrink-0">
        <Icon className="w-4 h-4 text-[#2E5D4F]" />
      </div>
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wider text-token-muted">{label}</div>
        <div className="font-semibold text-token-primary truncate">{value || '—'}</div>
      </div>
    </div>
  );
}
