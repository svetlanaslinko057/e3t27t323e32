import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatUAH, formatPercent, formatDateUk } from '@/lib/lumenApi';
import { Search } from 'lucide-react';

const STATUS_BADGE = {
  active:           { label: 'Активна',           cls: 'bg-emerald-100 text-emerald-800' },
  kyc_pending:      { label: 'Очікує KYC',        cls: 'bg-amber-100 text-amber-800' },
  contract_pending: { label: 'Очікує підпису',    cls: 'bg-sky-100 text-sky-800' },
  pending_payment:  { label: 'Очікує оплату',     cls: 'bg-sky-100 text-sky-800' },
  matured:          { label: 'Завершена',         cls: 'bg-muted text-muted-foreground' },
  exited:           { label: 'Вихід',             cls: 'bg-muted text-muted-foreground' },
  cancelled:        { label: 'Скасована',         cls: 'bg-red-100 text-red-700' },
};

export default function InvestorPortfolio() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');

  useEffect(() => {
    lumen.get('/investor/investments')
      .then((r) => setList(r.data?.items || []))
      .catch(() => setList([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = list.filter((i) => !q || i.asset_title?.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto" data-testid="investor-portfolio">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Портфель</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Мої інвестиції</h1>
        <p className="mt-1 text-muted-foreground">Повний список ваших позицій по всіх активах та раундах.</p>
      </header>

      <div className="mb-5 relative">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Пошук за назвою активу…"
          className="w-full pl-9 pr-4 h-11 rounded-xl border border-border bg-card focus:outline-none focus:border-[#2E5D4F] transition"
          data-testid="portfolio-search"
        />
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-24 bg-muted/40 rounded-2xl animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center">
          <p className="font-semibold">У вас ще немає інвестицій</p>
          <p className="text-sm text-muted-foreground mt-2">Почніть з активних раундів — вибір живих об'єктів в розділі «Об'єкти».</p>
          <Link to="/investor/opportunities" className="inline-flex mt-5 px-5 h-10 rounded-full bg-foreground text-background items-center font-medium hover:opacity-90">Переглянути об'єкти</Link>
        </div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-widest text-muted-foreground">
              <tr>
                <th className="text-left px-5 py-3 font-medium">Актив</th>
                <th className="text-left px-5 py-3 font-medium">Раунд</th>
                <th className="text-left px-5 py-3 font-medium">Статус</th>
                <th className="text-right px-5 py-3 font-medium">Сума</th>
                <th className="text-right px-5 py-3 font-medium">Частка</th>
                <th className="text-right px-5 py-3 font-medium">Дохідність</th>
                <th className="text-right px-5 py-3 font-medium">Дата</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((inv) => (
                <tr key={inv.id} className="hover:bg-muted/40 transition">
                  <td className="px-5 py-4">
                    <Link to={`/investor/assets/${inv.asset_id}`} className="font-medium hover:text-[#2E5D4F]">{inv.asset_title}</Link>
                    <p className="text-xs text-muted-foreground">{inv.asset_location}</p>
                  </td>
                  <td className="px-5 py-4 text-muted-foreground">{inv.round_label || '—'}</td>
                  <td className="px-5 py-4">
                    {(() => {
                      const b = STATUS_BADGE[inv.status] || { label: inv.status || '—', cls: 'bg-muted text-muted-foreground' };
                      return <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${b.cls}`} data-testid={`portfolio-status-${inv.id}`}>{b.label}</span>;
                    })()}
                  </td>
                  <td className="px-5 py-4 text-right font-mono font-semibold">{formatUAH(inv.invested_amount)}</td>
                  <td className="px-5 py-4 text-right">{(inv.share_percent || 0).toFixed(2)}%</td>
                  <td className="px-5 py-4 text-right text-[#2E5D4F]">+{formatPercent(inv.current_yield)}</td>
                  <td className="px-5 py-4 text-right text-muted-foreground">{formatDateUk(inv.invested_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
