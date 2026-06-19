/**
 * Admin · Finance Engine (D-block) — Live FX · Tax · Dividend Scheduler
 *   D3  FX rates (НБУ snapshot) + manual refresh + history
 *   D2  UA withholding tax config (ПДФО 18% + ВЗ 1.5%) + preview + liability
 *   D1  Dividend scheduler — due plans + manual run (catch-up)
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatUAH, formatDateUk } from '@/lib/lumenApi';
import {
  Loader2, RefreshCw, Banknote, Receipt, CalendarClock, AlertTriangle,
  TrendingUp, PlayCircle, CheckCircle2,
} from 'lucide-react';

const Card = ({ children, className = '' }) => (
  <div className={`rounded-2xl border border-border bg-card p-5 ${className}`}>{children}</div>
);

export default function AdminFinanceEngine() {
  const [tab, setTab] = useState('fx');
  const [err, setErr] = useState('');

  // FX
  const [fx, setFx] = useState(null);
  const [fxHistory, setFxHistory] = useState([]);
  const [fxBusy, setFxBusy] = useState(false);

  // Tax
  const [tax, setTax] = useState(null);
  const [taxLiab, setTaxLiab] = useState(null);
  const [preview, setPreview] = useState(null);
  const [previewGross, setPreviewGross] = useState('100000');
  const [pdfo, setPdfo] = useState('');
  const [vz, setVz] = useState('');
  const [taxBusy, setTaxBusy] = useState(false);

  // Scheduler
  const [due, setDue] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [schedBusy, setSchedBusy] = useState(false);

  const loadFx = useCallback(() => {
    lumen.get('/admin/fx/rates').then((r) => setFx(r.data)).catch((e) => setErr(lumenError(e)));
    lumen.get('/admin/fx/history').then((r) => setFxHistory(r.data.items || [])).catch(() => {});
  }, []);
  const loadTax = useCallback(() => {
    lumen.get('/admin/tax/config').then((r) => { setTax(r.data); setPdfo(String(r.data.pdfo_rate)); setVz(String(r.data.vz_rate)); }).catch((e) => setErr(lumenError(e)));
    lumen.get('/admin/tax/liability').then((r) => setTaxLiab(r.data)).catch(() => {});
  }, []);
  const loadDue = useCallback(() => {
    lumen.get('/admin/payout-scheduler/due').then((r) => setDue(r.data)).catch((e) => setErr(lumenError(e)));
  }, []);

  useEffect(() => {
    if (tab === 'fx') loadFx();
    if (tab === 'tax') loadTax();
    if (tab === 'scheduler') loadDue();
  }, [tab, loadFx, loadTax, loadDue]);

  const refreshFx = async () => {
    setFxBusy(true); setErr('');
    try { await lumen.post('/admin/fx/refresh'); loadFx(); }
    catch (e) { setErr(lumenError(e)); } finally { setFxBusy(false); }
  };

  const runPreview = async () => {
    try { const r = await lumen.get('/admin/tax/preview', { params: { gross: Number(previewGross) || 0 } }); setPreview(r.data); }
    catch (e) { setErr(lumenError(e)); }
  };
  const saveTax = async () => {
    setTaxBusy(true); setErr('');
    try { await lumen.put('/admin/tax/config', { pdfo_rate: Number(pdfo), vz_rate: Number(vz) }); loadTax(); }
    catch (e) { setErr(lumenError(e)); } finally { setTaxBusy(false); }
  };

  const runScheduler = async (autoCredit) => {
    setSchedBusy(true); setErr(''); setRunResult(null);
    try {
      const r = await lumen.post('/admin/payout-scheduler/run', { auto_credit: !!autoCredit });
      setRunResult(r.data); loadDue();
    } catch (e) { setErr(lumenError(e)); } finally { setSchedBusy(false); }
  };

  const TabBtn = ({ id, icon, label }) => (
    <button onClick={() => setTab(id)} data-testid={`finance-tab-${id}`}
      className={`inline-flex items-center gap-1.5 px-3 h-9 rounded-lg text-sm font-medium transition ${tab === id ? 'text-white' : 'text-muted-foreground hover:text-foreground'}`}
      style={tab === id ? { background: '#2E5D4F' } : {}}>{icon}{label}</button>
  );

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" data-testid="admin-finance-engine">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Finance Engine · D-block</div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-[#2E5D4F]" /> Курси · Податки · Планувальник виплат
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Живі курси НБУ · утримання ПДФО 18% + ВЗ 1.5% · автоматичне нарахування дивідендів.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-border pb-3">
        <TabBtn id="fx" icon={<Banknote className="w-4 h-4" />} label="Курси валют (FX)" />
        <TabBtn id="tax" icon={<Receipt className="w-4 h-4" />} label="Податки" />
        <TabBtn id="scheduler" icon={<CalendarClock className="w-4 h-4" />} label="Планувальник" />
      </div>

      {err && <div className="rounded-lg bg-rose-50 text-rose-700 text-sm px-3 py-2 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{err}</div>}

      {/* ── FX ── */}
      {tab === 'fx' && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-center justify-between mb-3">
              <div className="font-semibold">Поточні курси (внутрішня база)</div>
              <button onClick={refreshFx} disabled={fxBusy} data-testid="fx-refresh"
                className="h-9 px-3 rounded-lg text-sm text-white inline-flex items-center gap-1.5 disabled:opacity-50" style={{ background: '#2E5D4F' }}>
                {fxBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Оновити з НБУ
              </button>
            </div>
            {!fx ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /> : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="fx-rates">
                {Object.entries(fx.rates || {}).map(([cc, rate]) => (
                  <div key={cc} className="rounded-xl border border-border p-3">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{cc} → база</div>
                    <div className="text-xl font-bold tabular-nums">{Number(rate).toFixed(4)}</div>
                  </div>
                ))}
                <div className="rounded-xl border border-dashed border-border p-3 col-span-full text-xs text-muted-foreground">
                  Джерело: <b>{fx.meta?.source}</b> · знімок: {formatDateUk(fx.meta?.fetched_at) || fx.meta?.date || '—'}
                </div>
              </div>
            )}
          </Card>
          <Card>
            <div className="font-semibold mb-2">Історія знімків</div>
            <div className="space-y-1 max-h-64 overflow-auto text-sm">
              {fxHistory.map((s) => (
                <div key={`${s.date}-${s.source}`} className="flex justify-between border-b border-border/50 py-1">
                  <span>{s.date} · <span className="text-muted-foreground uppercase text-xs">{s.source}</span></span>
                  <span className="font-mono text-xs">USD {Number(s.rates?.USD || 0).toFixed(2)} · EUR {Number(s.rates?.EUR || 0).toFixed(2)}</span>
                </div>
              ))}
              {fxHistory.length === 0 && <div className="text-muted-foreground">Немає знімків</div>}
            </div>
          </Card>
        </div>
      )}

      {/* ── TAX ── */}
      {tab === 'tax' && (
        <div className="grid md:grid-cols-2 gap-4">
          <Card>
            <div className="font-semibold mb-3">Ставки утримання (Україна)</div>
            {!tax ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /> : (
              <div className="space-y-3">
                <label className="block text-sm">ПДФО (частка)
                  <input value={pdfo} onChange={(e) => setPdfo(e.target.value)} type="number" step="0.001" data-testid="tax-pdfo"
                    className="mt-1 w-full h-10 rounded-lg border border-border bg-background px-3" />
                </label>
                <label className="block text-sm">Військовий збір (частка)
                  <input value={vz} onChange={(e) => setVz(e.target.value)} type="number" step="0.001" data-testid="tax-vz"
                    className="mt-1 w-full h-10 rounded-lg border border-border bg-background px-3" />
                </label>
                <div className="text-xs text-muted-foreground">Поточна ефективна ставка: <b>{(((tax.pdfo_rate || 0) + (tax.vz_rate || 0)) * 100).toFixed(1)}%</b></div>
                <button onClick={saveTax} disabled={taxBusy} data-testid="tax-save"
                  className="h-10 px-4 rounded-lg text-sm text-white inline-flex items-center gap-2 disabled:opacity-50" style={{ background: '#2E5D4F' }}>
                  {taxBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Зберегти
                </button>
              </div>
            )}
          </Card>
          <div className="space-y-4">
            <Card>
              <div className="font-semibold mb-3">Калькулятор утримання</div>
              <div className="flex gap-2">
                <input value={previewGross} onChange={(e) => setPreviewGross(e.target.value)} type="number" data-testid="tax-preview-gross"
                  className="flex-1 h-10 rounded-lg border border-border bg-background px-3" placeholder="Сума (gross)" />
                <button onClick={runPreview} data-testid="tax-preview-run"
                  className="h-10 px-4 rounded-lg text-sm border border-border hover:bg-muted">Розрахувати</button>
              </div>
              {preview && (
                <div className="mt-3 space-y-1 text-sm" data-testid="tax-preview-result">
                  <div className="flex justify-between"><span>Нараховано</span><span className="tabular-nums">{formatUAH(preview.gross)}</span></div>
                  <div className="flex justify-between text-amber-700"><span>ПДФО</span><span className="tabular-nums">−{formatUAH(preview.pdfo)}</span></div>
                  <div className="flex justify-between text-amber-700"><span>ВЗ</span><span className="tabular-nums">−{formatUAH(preview.vz)}</span></div>
                  <div className="flex justify-between font-semibold border-t border-border pt-1"><span>До виплати</span><span className="tabular-nums text-emerald-700">{formatUAH(preview.net)}</span></div>
                </div>
              )}
            </Card>
            <Card>
              <div className="font-semibold mb-1">Податкове зобовʼязання</div>
              <p className="text-xs text-muted-foreground mb-2">Утримано та підлягає перерахуванню до бюджету</p>
              <div className="text-2xl font-bold tabular-nums text-amber-800" data-testid="tax-liability">
                {taxLiab ? formatUAH(taxLiab.outstanding_liability_uah) : '—'}
              </div>
              <div className="text-xs text-muted-foreground">{taxLiab?.count || 0} проводок</div>
            </Card>
          </div>
        </div>
      )}

      {/* ── SCHEDULER ── */}
      {tab === 'scheduler' && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="font-semibold">Плани до нарахування зараз</div>
                <div className="text-xs text-muted-foreground">{due ? `${due.due_count} план(ів) очікують генерації` : '...'}</div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => runScheduler(false)} disabled={schedBusy} data-testid="scheduler-run"
                  className="h-9 px-3 rounded-lg text-sm text-white inline-flex items-center gap-1.5 disabled:opacity-50" style={{ background: '#2E5D4F' }}>
                  {schedBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />} Згенерувати (на схвалення)
                </button>
              </div>
            </div>
            {!due ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /> : due.items.length === 0 ? (
              <div className="text-sm text-muted-foreground py-6 text-center" data-testid="scheduler-empty">Немає планів до нарахування</div>
            ) : (
              <div className="rounded-xl border border-border overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-[11px] uppercase tracking-wide text-muted-foreground">
                    <tr><th className="text-left px-3 py-2">Актив</th><th className="text-left px-3 py-2">Тип</th><th className="text-left px-3 py-2">Частота</th><th className="text-right px-3 py-2">Очік. сума</th><th className="text-left px-3 py-2">Період</th></tr>
                  </thead>
                  <tbody>
                    {due.items.map((p) => (
                      <tr key={p.plan_id} className="border-t border-border" data-testid={`due-plan-${p.plan_id}`}>
                        <td className="px-3 py-2 font-medium">{p.asset_title || p.asset_id}</td>
                        <td className="px-3 py-2">{p.type}</td>
                        <td className="px-3 py-2">{p.frequency}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatUAH(p.expected_amount)}</td>
                        <td className="px-3 py-2 text-muted-foreground">{formatDateUk(p.due_period_date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          {runResult && (
            <Card data-testid="scheduler-result">
              <div className="font-semibold mb-2">Результат запуску</div>
              <div className="text-sm">Знайдено до нарахування: <b>{runResult.due}</b> · Сформовано пакетів: <b>{runResult.generated?.length || 0}</b> · Помилок: <b>{runResult.errors?.length || 0}</b></div>
              <div className="mt-2 space-y-1">
                {(runResult.generated || []).map((g) => (
                  <div key={g.batch_id} className="text-xs flex justify-between border-b border-border/50 py-1">
                    <span>{g.asset} · {g.period}</span>
                    <span className="tabular-nums">net {formatUAH(g.total_net_uah)} · tax {formatUAH(g.total_tax_uah)}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
