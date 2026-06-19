import { useEffect, useState } from 'react';
import { lumen, formatDateUk } from '@/lib/lumenApi';
import { Bell, CheckCheck } from 'lucide-react';

export default function InvestorNotifications() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/investor/notifications')
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const markAll = async () => {
    try {
      await lumen.post('/investor/notifications/read-all');
      setItems((prev) => prev.map((i) => ({ ...i, read: true })));
    } catch (_e) { /* ignore */ }
  };

  return (
    <div className="p-6 md:p-10 max-w-3xl mx-auto" data-testid="investor-notifications">
      <header className="mb-8 flex items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Сповіщення</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Сповіщення та події</h1>
        </div>
        {items.some((i) => !i.read) && (
          <button onClick={markAll} className="text-sm inline-flex items-center gap-1.5 text-[#2E5D4F] hover:underline" data-testid="mark-all-read">
            <CheckCheck className="w-4 h-4" /> Позначити як прочитані
          </button>
        )}
      </header>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-muted/40 animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center">
          <Bell className="w-8 h-8 mx-auto text-muted-foreground" />
          <p className="font-semibold mt-3">Поки тихо</p>
          <p className="text-sm text-muted-foreground mt-2">Сповіщення про нові виплати, звіти та події раундів будуть тут.</p>
        </div>
      ) : (
        <ul className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden">
          {items.map((n) => (
            <li key={n.id} className={`px-5 py-4 ${n.read ? '' : 'bg-[#2E5D4F]/5'}`}>
              <div className="flex items-start gap-3">
                {!n.read && <span className="w-2 h-2 rounded-full bg-[#2E5D4F] mt-2 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <p className="font-medium">{n.title}</p>
                  <p className="text-sm text-muted-foreground mt-0.5">{n.body}</p>
                  <p className="text-[11px] text-muted-foreground mt-1.5">{formatDateUk(n.created_at)}</p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
