import { useCallback, useEffect, useState } from 'react';
import { lumen, lumenError, formatUAH, formatDateUk, UAH_PER_USD } from '@/lib/lumenApi';
import { Landmark, Loader2, Plus, X, Users, Coins, TrendingUp, ChevronRight, Wallet, Calculator, CheckCircle2 } from 'lucide-react';

const PRIMARY = '#2E5D4F';

export default function AdminFundLpgp() {
  const [funds, setFunds] = useState([]);
  const [sel, setSel] = useState('');
  const [summary, setSummary] = useState(null);
  const [tab, setTab] = useState('commitments');
  const [commitments, setCommitments] = useState([]);
  const [calls, setCalls] = useState([]);
  const [distros, setDistros] = useState([]);
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ investor_id: '', amount_uah: '', role: 'LP' });
  const [callForm, setCallForm] = useState({ percent: '20', note: '' });
  const [distForm, setDistForm] = useState({ income_uah: '', expenses_uah: '0', pref_rate: '0.08', carry_rate: '0.20', note: '' });
  const [preview, setPreview] = useState(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    lumen.get('/admin/institutional/funds').then((r) => {
      const list = r.data.items || []; setFunds(list);
      if (list[0]) setSel(list[0].id);
    });
    lumen.get('/admin/investors').then((r) => setUsers(r.data.items || r.data || [])).catch(() => {});
  }, []);

  const loadAll = useCallback(async () => {
    if (!sel) return;
    setLoading(true); setErr('');
    try {
      const [s, c, k, d] = await Promise.all([
        lumen.get(`/admin/funds/${sel}/summary`),
        lumen.get(`/admin/funds/${sel}/commitments`),
        lumen.get(`/admin/funds/${sel}/calls`),
        lumen.get(`/admin/funds/${sel}/distributions`),
      ]);
      setSummary(s.data); setCommitments(c.data.items || []);
      setCalls(k.data.items || []); setDistros(d.data.items || []);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, [sel]);
  useEffect(() => { if (sel) loadAll(); }, [sel, loadAll]);

  const addCommit = async () => {
    if (!form.investor_id || !form.amount_uah) { setErr('Оберіть інвестора та суму'); return; }
    setBusy(true); setErr('');
    try {
      await lumen.post(`/admin/funds/${sel}/commitments`, { ...form, amount_uah: Number(form.amount_uah) * UAH_PER_USD });
      setForm({ investor_id: '', amount_uah: '', role: 'LP' }); loadAll();
    } catch (e) { setErr(lumenError(e)); }
    finally { setBusy(false); }
  };

  const removeCommit = async (cid) => {
    if (!window.confirm('Видалити?')) return;
    try { await lumen.delete(`/admin/funds/${sel}/commitments/${cid}`); loadAll(); }
    catch (e) { alert(lumenError(e)); }
  };

  const createCall = async () => {
    setBusy(true); setErr('');
    try {
      await lumen.post(`/admin/funds/${sel}/calls`, { percent: Number(callForm.percent), note: callForm.note });
      setCallForm({ percent: '20', note: '' }); loadAll();
    } catch (e) { setErr(lumenError(e)); }
    finally { setBusy(false); }
  };

  const markPaid = async (callId, lineId) => {
    try { await lumen.post(`/admin/calls/${callId}/lines/${lineId}/mark-paid`); loadAll(); }
    catch (e) { alert(lumenError(e)); }
  };

  const previewDistribution = async () => {
    setBusy(true); setErr(''); setPreview(null);
    try {
      const r = await lumen.post(`/admin/funds/${sel}/distributions/preview`, {
        income_uah: Number(distForm.income_uah || 0) * UAH_PER_USD,
        expenses_uah: Number(distForm.expenses_uah || 0) * UAH_PER_USD,
        pref_rate: Number(distForm.pref_rate || 0),
        carry_rate: Number(distForm.carry_rate || 0),
      });
      setPreview(r.data);
    } catch (e) { setErr(lumenError(e)); }
    finally { setBusy(false); }
  };

  const applyDistribution = async () => {
    if (!window.confirm('Застосувати виплату? Ця дія окончательна.')) return;
    setBusy(true); setErr('');
    try {
      await lumen.post(`/admin/funds/${sel}/distributions/apply`, {
        income_uah: Number(distForm.income_uah || 0) * UAH_PER_USD,
        expenses_uah: Number(distForm.expenses_uah || 0) * UAH_PER_USD,
        pref_rate: Number(distForm.pref_rate || 0),
        carry_rate: Number(distForm.carry_rate || 0),
        note: distForm.note,
      });
      setPreview(null);
      setDistForm({ income_uah: '', expenses_uah: '0', pref_rate: '0.08', carry_rate: '0.20', note: '' });
      loadAll();
    } catch (e) { setErr(lumenError(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-5" data-testid="admin-fund-lpgp">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">LP/GP Engine · G13</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Landmark className="w-5 h-5 text-[#2E5D4F]" /> Фонд · GP / LP консоль</h1>
        <p className="text-sm text-muted-foreground mt-1">Commitments → Capital Calls → Distributions (waterfall: RoC → Pref → Carry → Residual).</p>
      </div>

      <select value={sel} onChange={(e) => setSel(e.target.value)} data-testid="lpgp-fund-select"
        className="h-10 rounded-lg border border-border bg-background px-2 text-sm w-full md:w-96">
        {funds.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
      </select>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="lpgp-summary">
          <Kpi label="Зобов'язання" value={formatUAH(summary.committed_uah)} sub={`${summary.lp_count} LP · ${summary.gp_count} GP`} />
          <Kpi label="Сплачено" value={formatUAH(summary.paid_uah)} sub={`викликано ${formatUAH(summary.called_uah)}`} />
          <Kpi label="Невикликано" value={formatUAH(summary.uncalled_uah)} />
          <Kpi label="NAV" value={formatUAH(summary.nav_uah)} sub={`виплат ${formatUAH(summary.distributions_uah)}`} />
        </div>
      )}

      <div className="flex gap-2 border-b border-border" data-testid="lpgp-tabs">
        {[['commitments', 'Commitments', Users], ['calls', 'Capital Calls', Coins], ['distributions', 'Distributions', Wallet]].map(([v, l, I]) => (
          <button key={v} onClick={() => setTab(v)} data-testid={`lpgp-tab-${v}`}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px inline-flex items-center gap-1.5 ${tab === v ? 'border-[#2E5D4F] text-[#2E5D4F]' : 'border-transparent text-muted-foreground'}`}>
            <I className="w-4 h-4" />{l}
          </button>
        ))}
      </div>

      {loading && <div className="py-8 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>}
      {err && <p className="text-sm text-rose-600">{err}</p>}

      {tab === 'commitments' && (
        <>
          <section className="rounded-2xl border border-border bg-card p-5" data-testid="commit-form">
            <div className="flex items-center gap-2 mb-3"><Plus className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Нове зобов'язання</h2></div>
            <div className="grid md:grid-cols-4 gap-2 items-end">
              <div><label className="text-[11px] uppercase text-muted-foreground">Інвестор</label>
                <select value={form.investor_id} onChange={(e) => setForm({ ...form, investor_id: e.target.value })} data-testid="commit-investor"
                  className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
                  <option value="">— виберіть —</option>
                  {users.map((u) => <option key={u.user_id || u.id} value={u.user_id || u.id}>{u.full_name || u.name || u.email}</option>)}
                </select>
              </div>
              <div><label className="text-[11px] uppercase text-muted-foreground">Сума, $</label>
                <input type="number" value={form.amount_uah} onChange={(e) => setForm({ ...form, amount_uah: e.target.value })} data-testid="commit-amount"
                  className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
              </div>
              <div><label className="text-[11px] uppercase text-muted-foreground">Роль</label>
                <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} data-testid="commit-role"
                  className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1"><option value="LP">LP</option><option value="GP">GP</option></select>
              </div>
              <button onClick={addCommit} disabled={busy} data-testid="commit-create"
                className="h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: PRIMARY }}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Додати
              </button>
            </div>
          </section>
          <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="commit-list">
            <table className="w-full text-sm">
              <thead className="bg-muted/40"><tr><th className="text-left px-4 py-2">Інвестор</th><th className="text-left px-4 py-2">Роль</th><th className="text-right px-4 py-2">Зобов'язання</th><th className="text-right px-4 py-2">Сплачено</th><th className="text-right px-4 py-2">Невикликано</th><th></th></tr></thead>
              <tbody>{commitments.map((c) => (
                <tr key={c.id} className="border-t border-border" data-testid={`commit-row-${c.id}`}>
                  <td className="px-4 py-2">{c.investor_name || c.investor_id}</td>
                  <td className="px-4 py-2"><span className={`text-[11px] px-2 py-0.5 rounded-full ${c.role === 'GP' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>{c.role}</span></td>
                  <td className="px-4 py-2 text-right font-mono">{formatUAH(c.amount_uah)}</td>
                  <td className="px-4 py-2 text-right font-mono text-emerald-600">{formatUAH(c.paid_uah)}</td>
                  <td className="px-4 py-2 text-right font-mono text-muted-foreground">{formatUAH(c.uncalled_uah)}</td>
                  <td className="px-4 py-2 text-right"><button onClick={() => removeCommit(c.id)} className="text-rose-600 hover:underline"><X className="w-4 h-4" /></button></td>
                </tr>))}
                {commitments.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-sm text-muted-foreground">Ще немає зобов'язань.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'calls' && (
        <>
          <section className="rounded-2xl border border-border bg-card p-5" data-testid="call-form">
            <div className="flex items-center gap-2 mb-3"><Plus className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Новий capital call</h2></div>
            <div className="grid md:grid-cols-3 gap-2 items-end">
              <div><label className="text-[11px] uppercase text-muted-foreground">% від зобов'язання</label>
                <input type="number" value={callForm.percent} onChange={(e) => setCallForm({ ...callForm, percent: e.target.value })} data-testid="call-percent"
                  className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
              </div>
              <div className="md:col-span-1"><label className="text-[11px] uppercase text-muted-foreground">Нотатка</label>
                <input value={callForm.note} onChange={(e) => setCallForm({ ...callForm, note: e.target.value })}
                  className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
              </div>
              <button onClick={createCall} disabled={busy} data-testid="call-create"
                className="h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: PRIMARY }}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Coins className="w-4 h-4" />} Створити call
              </button>
            </div>
          </section>
          <div className="space-y-3" data-testid="call-list">
            {calls.map((c) => <CallRow key={c.id} call={c} onMarkPaid={markPaid} />)}
            {calls.length === 0 && <p className="text-sm text-muted-foreground text-center py-6">Ще не було capital calls.</p>}
          </div>
        </>
      )}

      {tab === 'distributions' && (
        <>
          <section className="rounded-2xl border border-border bg-card p-5" data-testid="dist-form">
            <div className="flex items-center gap-2 mb-3"><Calculator className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Waterfall — прев'ю і застосування</h2></div>
            <div className="grid md:grid-cols-4 gap-2 items-end">
              <Field label="Income, $" v={distForm.income_uah} ds="dist-income" onChange={(v) => setDistForm({ ...distForm, income_uah: v })} type="number" />
              <Field label="Expenses, $" v={distForm.expenses_uah} ds="dist-expenses" onChange={(v) => setDistForm({ ...distForm, expenses_uah: v })} type="number" />
              <Field label="Pref rate (0..1)" v={distForm.pref_rate} ds="dist-pref" onChange={(v) => setDistForm({ ...distForm, pref_rate: v })} type="number" step="0.01" />
              <Field label="Carry rate (0..1)" v={distForm.carry_rate} ds="dist-carry" onChange={(v) => setDistForm({ ...distForm, carry_rate: v })} type="number" step="0.01" />
            </div>
            <div className="mt-3 flex gap-2">
              <button onClick={previewDistribution} disabled={busy} data-testid="dist-preview"
                className="h-10 px-4 rounded-lg text-sm font-medium border border-border hover:bg-muted inline-flex items-center gap-1.5">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Calculator className="w-4 h-4" />} Прев'ю
              </button>
              {preview && (
                <button onClick={applyDistribution} disabled={busy} data-testid="dist-apply"
                  className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: PRIMARY }}>
                  <CheckCircle2 className="w-4 h-4" /> Застосувати
                </button>
              )}
            </div>
          </section>

          {preview && (
            <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="dist-preview-block">
              <div className="px-5 py-3 border-b border-border font-semibold flex items-center gap-1.5"><TrendingUp className="w-4 h-4 text-[#2E5D4F]" />Waterfall preview</div>
              <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <Kpi label="Net Income" value={formatUAH(preview.summary?.net_income_uah)} sub={`витрат ${formatUAH(preview.summary?.expenses_uah)}`} />
                <Kpi label="Return of Capital" value={formatUAH(preview.summary?.stage_return_of_capital_uah)} sub={`LP paid-in ${formatUAH(preview.summary?.lp_paid_in_uah)}`} />
                <Kpi label="Pref Return" value={formatUAH(preview.summary?.stage_preferred_return_uah)} sub={`@ ${(preview.summary?.pref_rate * 100).toFixed(1)}%`} />
                <Kpi label="Carry / Residual" value={`${formatUAH(preview.summary?.stage_carry_uah)} / ${formatUAH(preview.summary?.stage_residual_uah)}`} />
              </div>
              <table className="w-full text-sm">
                <thead className="bg-muted/40"><tr><th className="text-left px-4 py-2">Інвестор</th><th className="text-left px-4 py-2">Роль</th><th className="text-right px-4 py-2">RoC</th><th className="text-right px-4 py-2">Pref</th><th className="text-right px-4 py-2">Carry</th><th className="text-right px-4 py-2">Residual</th><th className="text-right px-4 py-2">Всього</th></tr></thead>
                <tbody>{(preview.lines || []).map((l, i) => (
                  <tr key={i} className="border-t border-border"><td className="px-4 py-2">{l.investor_name}</td><td className="px-4 py-2">{l.role}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(l.return_of_capital_uah)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(l.preferred_return_uah)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(l.carry_uah)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(l.residual_uah)}</td><td className="px-4 py-2 text-right font-mono font-semibold">{formatUAH(l.amount_uah)}</td></tr>))}
                </tbody>
              </table>
            </div>
          )}

          <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="dist-history">
            <div className="px-5 py-3 border-b border-border font-semibold">Історія виплат</div>
            {distros.length === 0 ? <p className="px-5 py-6 text-sm text-muted-foreground">Виплат ще не було.</p> : (
              <table className="w-full text-sm">
                <thead className="bg-muted/40"><tr><th className="text-left px-4 py-2">#</th><th className="text-left px-4 py-2">Дата</th><th className="text-right px-4 py-2">Net Income</th><th className="text-right px-4 py-2">Carry</th><th className="text-left px-4 py-2">Нотатка</th></tr></thead>
                <tbody>{distros.map((d) => (<tr key={d.id} className="border-t border-border"><td className="px-4 py-2">{d.seq}</td><td className="px-4 py-2">{formatDateUk(d.created_at)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(d.amount_uah)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(d.summary?.stage_carry_uah)}</td><td className="px-4 py-2 text-muted-foreground">{d.note || '—'}</td></tr>))}</tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({ label, value, sub }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-bold">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function Field({ label, v, onChange, ds, type = 'text', step }) {
  return (
    <div>
      <label className="text-[11px] uppercase text-muted-foreground">{label}</label>
      <input value={v} onChange={(e) => onChange(e.target.value)} type={type} step={step} data-testid={ds}
        className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
    </div>
  );
}

function CallRow({ call, onMarkPaid }) {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState(null);
  const toggle = async () => {
    if (!open && lines === null) {
      try { const r = await lumen.get(`/admin/funds/${call.fund_id}/calls/${call.id}`); setLines(r.data.lines || []); }
      catch (_e) {}
    }
    setOpen(!open);
  };
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden" data-testid={`call-${call.id}`}>
      <button onClick={toggle} className="w-full px-5 py-3 text-left flex items-center justify-between gap-3 hover:bg-muted/30">
        <div className="flex items-center gap-3">
          <span className="w-9 h-9 rounded-lg bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center font-bold">#{call.seq}</span>
          <div>
            <div className="font-semibold text-sm">{call.percent}% · {formatUAH(call.total_amount_uah)}</div>
            <div className="text-[11px] text-muted-foreground">{call.note || ''} · статус: {call.status}</div>
          </div>
        </div>
        <ChevronRight className={`w-4 h-4 text-muted-foreground transition ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && lines && (
        <table className="w-full text-sm border-t border-border">
          <thead className="bg-muted/30"><tr><th className="text-left px-4 py-2">Інвестор</th><th className="text-right px-4 py-2">Сума</th><th className="text-right px-4 py-2">Статус</th><th></th></tr></thead>
          <tbody>{lines.map((l) => (
            <tr key={l.id} className="border-t border-border"><td className="px-4 py-2">{l.investor_name}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(l.amount_uah)}</td>
              <td className="px-4 py-2 text-right"><span className={`text-[11px] px-2 py-0.5 rounded-full ${l.status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{l.status}</span></td>
              <td className="px-4 py-2 text-right">{l.status !== 'paid' && <button onClick={() => onMarkPaid(call.id, l.id)} data-testid={`call-paid-${l.id}`} className="text-[#2E5D4F] hover:underline text-xs inline-flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" />Оплачено</button>}</td>
            </tr>))}
          </tbody>
        </table>
      )}
    </div>
  );
}
