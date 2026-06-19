import { useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { VerifiedBadge, gradeTone, scoreTone } from '@/lib/operatorUi';
import { Loader2, Trophy, Building2, Users, ArrowLeft, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';

export default function OperatorLeaderboard() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.title = 'Lumen · Рейтинг операторів';
    lumen.get('/operators/leaderboard').then((r) => setItems(r.data.items || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="operator-leaderboard">
      <header className="border-b border-border">
        <div className="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
          <Link to="/"><Logo height={28} /></Link>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="w-4 h-4" /> На сайт</Link>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 py-10">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 text-[11px] uppercase tracking-widest text-muted-foreground border border-border rounded-full px-3 py-1"><Trophy className="w-3.5 h-3.5" /> Operator OS</div>
          <h1 className="text-3xl font-bold mt-4">Рейтинг операторів</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">Не гейміфікація — довіра. Рейтинг побудовано на фактах: своєчасність виплат, звітність, заповненість, ліквідність та настрій спільноти.</p>
        </div>

        {loading ? (
          <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>
        ) : (
          <div className="space-y-3" data-testid="leaderboard-list">
            {items.map((op) => (
              <div key={op.id} className="rounded-2xl border border-border bg-card p-5 flex items-center gap-5">
                <div className="w-10 text-center">
                  <div className="text-2xl font-bold text-muted-foreground">#{op.rank}</div>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold">{op.name}</h3>
                    <VerifiedBadge verified={op.verified} status={op.status} statusLabel={op.status_label} />
                  </div>
                  <div className="text-[12px] text-muted-foreground mt-0.5">{op.kind_label} · {op.region || '—'} · {op.specialization || '—'}</div>
                  <div className="flex flex-wrap gap-4 mt-3 text-[12px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1"><Building2 className="w-3.5 h-3.5" /> {op.kpi?.assets_count ?? 0} об'єктів</span>
                    <span className="inline-flex items-center gap-1"><Users className="w-3.5 h-3.5" /> {op.kpi?.investors_count ?? 0} інвесторів</span>
                    <span>AUM {formatUAH(op.kpi?.aum_uah)}</span>
                    <span>дохідність {formatPercent(op.kpi?.avg_yield_pct)}</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-3xl font-bold" style={{ color: scoreTone(op.reputation?.score) }}>{Math.round(op.reputation?.score ?? 0)}</div>
                  <div className={`text-sm font-semibold ${gradeTone(op.reputation?.grade)}`}>{op.reputation?.grade}</div>
                </div>
              </div>
            ))}
            {items.length === 0 && <p className="text-center text-muted-foreground py-12">Операторів ще немає.</p>}
          </div>
        )}

        <div className="mt-10 rounded-2xl border border-[#2E5D4F]/30 bg-[#2E5D4F]/[0.05] p-5 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-[#2E5D4F] mt-0.5" />
          <div className="text-sm text-muted-foreground">Бейдж <b className="text-foreground">Verified Operator</b> отримують оператори зі статусом «Перевірено» або «Затверджено» після проходження верифікації LUMEN.</div>
        </div>
      </div>
    </div>
  );
}
