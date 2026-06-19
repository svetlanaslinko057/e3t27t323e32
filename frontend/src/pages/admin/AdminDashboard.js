import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatUAH } from '@/lib/lumenApi';
import { Users, Building2, CircleDollarSign, BarChart3, Plus } from 'lucide-react';
import FundingPulse from '@/pages/funding/FundingPulse';

export default function AdminDashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    lumen.get('/admin/overview')
      .then((r) => setData(r.data))
      .catch(() => setData(null));
  }, []);

  const k = data?.kpi || {};

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-8" data-testid="admin-dashboard">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Огляд</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Панель фонду Lumen</h1>
          <p className="mt-1 text-token-muted">Операційний зріз платформи.</p>
        </div>
        <div className="flex gap-2">
          <Link to="/admin/assets/new" className="inline-flex items-center gap-1.5 px-4 h-10 rounded-full bg-token-primary text-token-on-primary font-medium text-sm hover:opacity-90 transition" style={{ background: 'var(--token-primary)', color: 'var(--token-on-primary)' }}><Plus className="w-4 h-4" /> Новий актив</Link>
        </div>
      </header>

      {/* H1.1.1 Funding Pulse \u2014 surfaces treasury KPIs at the top of admin dashboard */}
      <FundingPulse />

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi icon={<Users className="w-4 h-4" />} label="Інвесторів" value={k.investors_count ?? 0} hint="всього" />
        <Kpi icon={<Building2 className="w-4 h-4" />} label="Активів" value={k.assets_count ?? 0} hint="в роботі" />
        <Kpi icon={<CircleDollarSign className="w-4 h-4" />} label="Акумульовано" value={formatUAH(k.total_raised)} hint="всього залучено" />
        <Kpi icon={<BarChart3 className="w-4 h-4" />} label="Активних раундів" value={k.active_rounds ?? 0} hint="відкрито" />
      </section>

      <section className="grid lg:grid-cols-2 gap-6">
        <div className="rounded-2xl border border-token-border bg-app-surface p-6" style={{ border: '1px solid var(--token-border)' }}>
          <h2 className="font-semibold mb-3">Останні реєстрації</h2>
          {(data?.recent_investors || []).length === 0 ? (
            <p className="text-sm text-token-muted">Поки порожньо.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: 'var(--token-border)' }}>
              {data.recent_investors.slice(0, 5).map((u) => (
                <li key={u.id} className="py-3 flex items-center justify-between">
                  <div>
                    <p className="font-medium text-sm">{u.name}</p>
                    <p className="text-xs text-token-muted">{u.email}</p>
                  </div>
                  <span className="text-xs text-token-muted">{u.kyc_status || 'kyc: —'}</span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/admin/investors" className="mt-4 inline-block text-sm text-[#2E5D4F] hover:underline">Дивитись всі →</Link>
        </div>

        <div className="rounded-2xl border border-token-border bg-app-surface p-6" style={{ border: '1px solid var(--token-border)' }}>
          <h2 className="font-semibold mb-3">Активні раунди</h2>
          {(data?.active_rounds || []).length === 0 ? (
            <p className="text-sm text-token-muted">Немає відкритих раундів.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: 'var(--token-border)' }}>
              {data.active_rounds.slice(0, 5).map((r) => (
                <li key={r.id} className="py-3">
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-sm">{r.asset_title}</p>
                    <span className="text-xs font-mono">{r.progress_percent || 0}%</span>
                  </div>
                  <div className="mt-2 h-1.5 rounded-full bg-token-border overflow-hidden" style={{ background: 'var(--token-border)' }}>
                    <div className="h-full bg-[#2E5D4F]" style={{ width: `${r.progress_percent || 0}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
          <Link to="/admin/assets" className="mt-4 inline-block text-sm text-[#2E5D4F] hover:underline">Дивитись всі →</Link>
        </div>
      </section>
    </div>
  );
}

const Kpi = ({ icon, label, value, hint }) => (
  <div className="rounded-2xl p-5" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }}>
    <div className="flex items-center gap-2 text-token-muted">{icon}<span className="text-[11px] uppercase tracking-widest">{label}</span></div>
    <p className="mt-3 text-2xl font-bold">{value}</p>
    {hint && <p className="mt-1 text-xs text-token-muted">{hint}</p>}
  </div>
);
