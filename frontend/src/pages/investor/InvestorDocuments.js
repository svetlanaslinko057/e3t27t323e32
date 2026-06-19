import { useEffect, useState } from 'react';
import { lumen, formatDateUk } from '@/lib/lumenApi';
import { FileText, Download } from 'lucide-react';

export default function InvestorDocuments() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/investor/documents')
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto" data-testid="investor-documents">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Документи</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Мої документи</h1>
        <p className="mt-1 text-muted-foreground">Договори участі, акти, звіти та підтвердження платежів.</p>
      </header>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-muted/40 animate-pulse" />)}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center">
          <p className="font-semibold">Документів ще немає</p>
          <p className="text-sm text-muted-foreground mt-2">Документи з'являтимуться тут після оформлення першої позиції.</p>
        </div>
      ) : (
        <ul className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden">
          {items.map((d) => (
            <li key={d.id} className="px-5 py-4 flex items-center gap-4 hover:bg-muted/40 transition">
              <div className="w-10 h-10 rounded-xl bg-muted flex items-center justify-center text-muted-foreground"><FileText className="w-5 h-5" /></div>
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{d.title}</p>
                <p className="text-xs text-muted-foreground">{d.kind_label || d.kind} · {formatDateUk(d.created_at)}</p>
              </div>
              <a
                href={d.url || '#'}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-4 h-9 rounded-full border border-border hover:border-[#2E5D4F] hover:text-[#2E5D4F] text-sm transition"
              >
                <Download className="w-3.5 h-3.5" /> Скачати
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
