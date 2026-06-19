import { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { lumen, formatUAH, formatPercent, formatDateUk, lumenError } from '@/lib/lumenApi';
import { ECONOMICS_SCENARIOS, applyScenario } from '@/lib/lumenEconomics';
import {
  ArrowLeft, MapPin, Building2, Calendar, ShieldCheck, FileText, BarChart3,
  TrendingUp, Receipt, Percent, AlertTriangle, Landmark, Pin, Lock, Download,
  MessageCircleQuestion, Users, LogIn, Loader2, CheckCircle2, PlayCircle,
} from 'lucide-react';
import { useAuth } from '@/App';
import {
  useAssetIntelligence, IntelligencePanel, InvestmentThesis, ScenarioEngine,
  CapitalStack, AssetJournal, SimilarAssets, ConvictionBadge, LiquidityBadge,
  AssetSnapshot, WhyWeInvested, CashFlow, RoundsTimeline,
} from '@/components/lumen/AssetIntelligence';
import AssetCommunity from '@/components/lumen/AssetCommunity';
import OperatorCard from '@/components/lumen/OperatorCard';
import AssetLiquidity from '@/components/lumen/AssetLiquidity';
import { trackEvent } from '@/lib/activityTracker';

const SEVERITY_BADGE = {
  low:    { label: 'низький',  cls: 'bg-emerald-100 text-emerald-800' },
  medium: { label: 'середній', cls: 'bg-amber-100 text-amber-800' },
  high:   { label: 'високий',  cls: 'bg-red-100 text-red-700' },
};

export default function InvestorAssetDetail() {
  const { assetId } = useParams();
  const { user } = useAuth();
  const [asset, setAsset] = useState(null);
  const [spv, setSpv] = useState(null);
  const [updates, setUpdates] = useState([]);
  const [reports, setReports] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [intentDone, setIntentDone] = useState(false);
  const [error, setError] = useState(null);
  const [mainImage, setMainImage] = useState(0);
  const [payoutSummary, setPayoutSummary] = useState(null);
  const [eligibility, setEligibility] = useState(null);
  const { intel, journal, similar } = useAssetIntelligence(assetId);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([
      lumen.get(`/assets/${assetId}`).catch(() => null),
      lumen.get(`/assets/${assetId}/spv`).catch(() => null),
      lumen.get(`/assets/${assetId}/updates`).catch(() => null),
      lumen.get(`/assets/${assetId}/reports`).catch(() => null),
      lumen.get(`/assets/${assetId}/documents`).catch(() => null),
      lumen.get(`/assets/${assetId}/questions`).catch(() => null),
      lumen.get(`/assets/${assetId}/payout-summary`).catch(() => null),
      lumen.get(`/investor/eligibility`, { params: { asset_id: assetId } }).catch(() => null),
    ]).then(([a, s, u, r, d, q, ps, el]) => {
      if (!alive) return;
      setAsset(a?.data || null);
      setSpv(s?.data?.spv || null);
      setUpdates(u?.data?.items || []);
      setReports(r?.data?.items || []);
      setDocuments(d?.data?.items || []);
      setQuestions(q?.data?.items || []);
      setPayoutSummary(ps?.data || null);
      setEligibility(el?.data || null);
      try { trackEvent('asset_view', { asset_id: assetId, surface: 'investor', title: a?.data?.title }); } catch (_) {}
    }).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [assetId, user]);

  const gallery = useMemo(() => {
    const g = Array.isArray(asset?.gallery) && asset.gallery.length > 0
      ? asset.gallery
      : (asset?.cover_url ? [{ url: asset.cover_url, caption: asset?.title }] : []);
    return g;
  }, [asset]);

  const refreshQuestions = () =>
    lumen.get(`/assets/${assetId}/questions`)
      .then((r) => setQuestions(r.data?.items || []))
      .catch(() => {});

  const submitIntent = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await lumen.post('/investor/intent', { asset_id: assetId, amount: Number(amount) });
      setIntentDone(true);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Не вдалося відправити. Спробуйте знову.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="p-10"><div className="h-8 w-64 bg-muted animate-pulse rounded" /></div>;
  }
  if (!asset) {
    return (
      <div className="p-10 text-center" data-testid="asset-not-found">
        <p className="font-semibold">Об'єкт не знайдено</p>
        <Link to="/investor/opportunities" className="text-[#2E5D4F] mt-2 inline-block">Повернутися до переліку</Link>
      </div>
    );
  }

  const TABS = [
    { key: 'overview', label: 'Огляд' },
    { key: 'liquidity', label: 'Ліквідність' },
    { key: 'community', label: 'Спільнота' },
    { key: 'journal', label: `Шлях активу${journal?.length ? ` (${journal.length})` : ''}` },
    { key: 'updates', label: `Оновлення${updates.length ? ` (${updates.length})` : ''}` },
    { key: 'docs', label: `Звіти й документи${(reports.length + documents.length) ? ` (${reports.length + documents.length})` : ''}` },
    { key: 'qa', label: `Питання${questions.length ? ` (${questions.length})` : ''}` },
  ];

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto" data-testid="asset-detail">
      <Link to="/investor/opportunities" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6">
        <ArrowLeft className="w-4 h-4" /> Назад до об'єктів
      </Link>

      <div className="grid lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          {/* ═══ Gallery ═══ */}
          <div data-testid="asset-gallery">
            <div
              className="aspect-[16/9] rounded-2xl bg-muted overflow-hidden border border-border"
              style={gallery[mainImage]?.url ? { backgroundImage: `url(${gallery[mainImage].url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}
              data-testid="asset-gallery-main"
            >
              {!gallery[mainImage]?.url && <div className="w-full h-full flex items-center justify-center text-muted-foreground"><Building2 className="w-24 h-24" /></div>}
            </div>
            {gallery.length > 1 && (
              <div className="mt-2 flex gap-2 overflow-x-auto pb-1" data-testid="asset-gallery-thumbs">
                {gallery.map((g, i) => (
                  <button
                    key={i}
                    onClick={() => setMainImage(i)}
                    title={g.caption}
                    className={`shrink-0 w-24 h-16 rounded-lg overflow-hidden border-2 transition ${i === mainImage ? 'border-[#2E5D4F]' : 'border-transparent opacity-70 hover:opacity-100'}`}
                    style={{ backgroundImage: `url(${g.url})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
                    data-testid={`gallery-thumb-${i}`}
                  />
                ))}
              </div>
            )}
            {gallery[mainImage]?.caption && (
              <p className="mt-1.5 text-xs text-muted-foreground">{gallery[mainImage].caption}</p>
            )}
          </div>

          <div>
            <span className="inline-block px-3 py-1 text-[10px] uppercase tracking-widest rounded-full bg-[#2E5D4F]/10 text-[#2E5D4F] border border-[#2E5D4F]/30">{asset.category_label || asset.category}</span>
            <h1 className="mt-3 text-3xl md:text-4xl font-bold tracking-tight">{asset.title}</h1>
            <p className="mt-2 text-muted-foreground flex items-center gap-2"><MapPin className="w-4 h-4" /> {asset.location}</p>
            {intel && (
              <div className="mt-3 flex items-center gap-2 flex-wrap">
                {intel.conviction && <ConvictionBadge score={intel.conviction.score} band={intel.conviction.band} label={intel.conviction.label} />}
                {intel.liquidity && <LiquidityBadge score={intel.liquidity.score} band={intel.liquidity.band} label={intel.liquidity.label} />}
              </div>
            )}
          </div>

          {/* ═══ Tabs ═══ */}
          <div className="flex gap-2 flex-wrap border-b border-border pb-3" data-testid="asset-tabs">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`px-4 h-9 rounded-full text-sm font-medium border transition ${tab === t.key ? 'bg-foreground text-background border-foreground' : 'border-border hover:border-[#2E5D4F]'}`}
                data-testid={`asset-tab-${t.key}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'overview' && (
            <OverviewTab asset={asset} assetId={assetId} amount={amount} spv={spv} intel={intel} similar={similar} />
          )}
          {tab === 'community' && <AssetCommunity assetId={assetId} user={user} basePath="investor" />}
          {tab === 'liquidity' && <AssetLiquidity assetId={assetId} user={user} />}
          {tab === 'journal' && <AssetJournal items={journal} />}
          {tab === 'updates' && <UpdatesTab updates={updates} />}
          {tab === 'docs' && <DocsTab reports={reports} documents={documents} user={user} />}
          {tab === 'qa' && (
            <QaTab assetId={assetId} questions={questions} user={user} onAsked={refreshQuestions} />
          )}
        </div>

        {/* ═══ Invest sidebar ═══ */}
        <aside className="space-y-4">
          <OperatorCard assetId={assetId} />
          <div className="rounded-2xl border border-border bg-card p-6 sticky top-6">
            <p className="text-xs uppercase tracking-widest text-muted-foreground">Мінімальний вхід</p>
            <p className="mt-2 text-3xl font-bold">{formatUAH(asset.min_ticket)}</p>
            <div className="mt-5 space-y-2 text-sm">
              <Row label="Зібрано" value={`${asset.progress_percent || 0}%`} />
              <Row label="Обсяг раунду" value={formatUAH(asset.round_target)} />
              <Row label="Дедлайн раунду" value={formatDateUk(asset.round_deadline)} />
              <Row label="Учасників" value={asset.investors_count || 0} />
            </div>
            <div className="mt-5">
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div className="h-full bg-[#2E5D4F] transition-all" style={{ width: `${asset.progress_percent || 0}%` }} />
              </div>
            </div>
            <div className="mt-6 pt-6 border-t border-border">
              {eligibility && eligibility.access_level !== 'retail_allowed' && (
                <div className={`mb-4 rounded-xl border p-3 text-xs ${eligibility.eligible ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-900'}`} data-testid="eligibility-banner">
                  <div className="font-semibold flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    {eligibility.access_level_label}
                  </div>
                  {eligibility.eligible ? (
                    <p className="mt-1">Ви маєте право інвестувати в цей об'єкт (рівень: {eligibility.your_level_label}).</p>
                  ) : (
                    <>
                      <p className="mt-1">{eligibility.blockers?.[0] || `Потрібен рівень «${eligibility.required_level_label}».`}</p>
                      <Link to="/investor/accreditation" className="mt-1 inline-block underline font-medium">Пройти акредитацію →</Link>
                    </>
                  )}
                </div>
              )}
              <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Ваша сума інвестування</p>
              <input
                type="number"
                inputMode="numeric"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder={`від ${formatUAH(asset.min_ticket)}`}
                className="w-full h-12 px-4 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F]"
                disabled={intentDone}
                data-testid="intent-amount"
              />
              {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
              {intentDone ? (
                <div className="mt-3 p-3 rounded-xl bg-[#2E5D4F]/10 text-sm">
                  <p className="font-medium">Дякуємо. Ми отримали ваш намір.</p>
                  <p className="text-muted-foreground mt-1">Після підтвердження оператором вам буде згенеровано договір на підпис.</p>
                </div>
              ) : (
                <button
                  onClick={submitIntent}
                  disabled={!amount || Number(amount) < (asset.min_ticket || 0) || submitting || !user || (eligibility && !eligibility.eligible)}
                  className="mt-3 w-full h-12 rounded-xl bg-foreground text-background font-medium disabled:opacity-50 hover:opacity-90 transition"
                  data-testid="submit-intent"
                >
                  {!user ? 'Увійдіть, щоб інвестувати' : (eligibility && !eligibility.eligible) ? 'Потрібна акредитація' : submitting ? 'Надсилання…' : 'Інвестувати'}
                </button>
              )}
              <p className="mt-3 text-[11px] text-muted-foreground leading-relaxed">
                Це вираження наміру, а не платіж. Договір участі підписується окремо після підтвердження оператором.
              </p>
            </div>
          </div>

          {payoutSummary && (payoutSummary.total_accrued > 0 || payoutSummary.next_payout) && (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-5" data-testid="asset-payout-summary">
              <p className="text-xs uppercase tracking-widest text-emerald-800/80 flex items-center gap-1.5">
                <TrendingUp className="w-3.5 h-3.5" /> Дохідність активу
              </p>
              <div className="mt-3 space-y-2 text-sm">
                <Row label="Всього нараховано" value={formatUAH(payoutSummary.total_accrued)} />
                <Row label="Остання виплата" value={payoutSummary.last_payout ? formatDateUk(payoutSummary.last_payout) : '—'} />
                <Row label="Наступна виплата" value={payoutSummary.next_payout ? formatDateUk(payoutSummary.next_payout) : '—'} />
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

/* ────────────────────────────── Overview ────────────────────────────── */

function OverviewTab({ asset, assetId, amount, spv, intel, similar }) {
  return (
    <div className="space-y-6" data-testid="asset-overview">
      {/* ═══ B5a Snapshot (at-a-glance scoring) ═══ */}
      {intel?.snapshot && <AssetSnapshot snapshot={intel.snapshot} />}

      {/* ═══ B5b Why we invested ═══ */}
      {intel?.highlights?.length > 0 && <WhyWeInvested highlights={intel.highlights} />}

      {/* ═══ B5+B6+B7 Intelligence panel ═══ */}
      {intel && (
        <IntelligencePanel metrics={intel.metrics} conviction={intel.conviction} liquidity={intel.liquidity} />
      )}

      {/* ═══ B5c Operating cash-flow + B5d Rounds ═══ */}
      {intel?.cashflow && <CashFlow data={intel.cashflow} />}
      {intel?.rounds && <RoundsTimeline data={intel.rounds} />}

      <div className="rounded-2xl border border-border bg-card p-6">
        <h2 className="font-semibold mb-2">Про об'єкт</h2>
        <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">{asset.description}</p>
      </div>

      {/* ═══ B1 Investment Thesis ═══ */}
      {intel?.thesis && <InvestmentThesis thesis={intel.thesis} />}

      <div className="grid sm:grid-cols-3 gap-3">
        <Pill icon={<BarChart3 className="w-4 h-4" />} label="Цільова дохідність" value={formatPercent(asset.target_yield)} />
        <Pill icon={<Calendar className="w-4 h-4" />} label="Горизонт" value={asset.horizon_label || `${asset.horizon_months || 12} міс.`} />
        <Pill icon={<ShieldCheck className="w-4 h-4" />} label="Юроболонка" value={spv?.name || asset.spv_label || 'SPV'} />
      </div>

      {/* ═══ B2 Scenario Engine ═══ */}
      {intel?.scenarios && <ScenarioEngine data={intel.scenarios} />}

      {/* ═══ B3 Capital Stack ═══ */}
      {intel?.capital_stack && <CapitalStack data={intel.capital_stack} />}

      {/* Videos */}
      {Array.isArray(asset.videos) && asset.videos.length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-6" data-testid="asset-videos">
          <h2 className="font-semibold mb-4 flex items-center gap-2"><PlayCircle className="w-4 h-4 text-[#2E5D4F]" /> Відеоогляди</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            {asset.videos.map((v, i) => (
              <div key={i}>
                <div className="aspect-video rounded-xl overflow-hidden border border-border bg-muted">
                  <iframe
                    src={v.embed_url}
                    title={v.title || `Відео ${i + 1}`}
                    className="w-full h-full"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                    loading="lazy"
                  />
                </div>
                {v.title && <p className="mt-1.5 text-xs text-muted-foreground">{v.title}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Economics (server-driven) */}
      <Economics assetId={assetId} amount={amount} />

      {/* Team */}
      {Array.isArray(asset.team) && asset.team.length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-6" data-testid="asset-team">
          <h2 className="font-semibold mb-4 flex items-center gap-2"><Users className="w-4 h-4 text-[#2E5D4F]" /> Команда проєкту</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            {asset.team.map((m, i) => (
              <div key={i} className="flex gap-3 p-3 rounded-xl border border-border bg-background/40">
                <div className="w-11 h-11 rounded-full bg-[#2E5D4F]/10 border border-[#2E5D4F]/20 flex items-center justify-center font-semibold text-[#2E5D4F] shrink-0 overflow-hidden"
                  style={m.photo_url ? { backgroundImage: `url(${m.photo_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}>
                  {!m.photo_url && (m.name || '?')[0]}
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-sm">{m.name}</p>
                  {m.role && <p className="text-xs text-[#2E5D4F]">{m.role}</p>}
                  {m.bio && <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{m.bio}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Risks (dynamic) */}
      {Array.isArray(asset.risks) && asset.risks.length > 0 && (
        <div className="rounded-2xl border border-[#C99B3D]/30 bg-[#C99B3D]/5 p-6" data-testid="asset-risks">
          <h2 className="font-semibold mb-4 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-[#C99B3D]" /> Ризики, які варто знати</h2>
          <ul className="space-y-3">
            {asset.risks.map((r, i) => {
              const sev = SEVERITY_BADGE[r.severity] || SEVERITY_BADGE.medium;
              return (
                <li key={i} className="text-sm">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">{r.title}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${sev.cls}`}>{sev.label}</span>
                  </div>
                  {r.description && <p className="text-muted-foreground mt-0.5 leading-relaxed">{r.description}</p>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Exit strategy */}
      {asset.exit_strategy && (
        <div className="rounded-2xl border border-border bg-card p-6" data-testid="asset-exit">
          <h2 className="font-semibold mb-2 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-[#2E5D4F]" /> Стратегія виходу</h2>
          <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">{asset.exit_strategy}</p>
        </div>
      )}

      {/* SPV card */}
      <div className="rounded-2xl border border-border bg-card p-6" data-testid="asset-spv">
        <h2 className="font-semibold mb-3 flex items-center gap-2"><Landmark className="w-4 h-4 text-[#2E5D4F]" /> Юридична структура (SPV)</h2>
        {spv ? (
          <div className="text-sm space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium">{spv.name}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${spv.status === 'active' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>{spv.status_label}</span>
            </div>
            {spv.registration_number && (
              <p className="text-muted-foreground">ЄДРПОУ: <span className="font-mono">{spv.registration_number}</span> · юрисдикція: {spv.jurisdiction}</p>
            )}
            <p className="text-muted-foreground leading-relaxed mt-2">
              На цей актив створено окрему юридичну особу. Усі кошти інвесторів зберігаються на окремому рахунку SPV, відокремлено від коштів платформи. Ваша частка пропорційна внеску та оформлена корпоративним договором.
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {asset.spv_label || 'Юридична оболонка формується.'}
          </p>
        )}
      </div>

      {/* ═══ B8 Similar Assets ═══ */}
      <SimilarAssets items={similar} basePath="/investor/assets" />
    </div>
  );
}

/* ────────────────────────────── Updates ────────────────────────────── */

const KIND_CHIP = {
  milestone: 'bg-[#2E5D4F]/10 text-[#2E5D4F]',
  news: 'bg-sky-100 text-sky-800',
  general: 'bg-muted text-muted-foreground',
};

function UpdatesTab({ updates }) {
  if (updates.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="updates-empty">
        Оновлень ще немає — оператор публікуватиме хід проєкту тут.
      </div>
    );
  }
  return (
    <div className="space-y-4" data-testid="asset-updates">
      {updates.map((u) => (
        <article key={u.id} className="rounded-2xl border border-border bg-card p-5" data-testid={`update-${u.id}`}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium uppercase tracking-wider ${KIND_CHIP[u.kind] || KIND_CHIP.general}`}>{u.kind_label}</span>
            {u.pinned && <Pin className="w-3.5 h-3.5 text-[#C99B3D]" />}
            <span className="text-xs text-muted-foreground ml-auto">{formatDateUk(u.published_at)}</span>
          </div>
          <h3 className="mt-2 font-semibold">{u.title}</h3>
          <p className="mt-1 text-sm text-muted-foreground leading-relaxed whitespace-pre-line">{u.body}</p>
        </article>
      ))}
    </div>
  );
}

/* ─────────────────────── Reports & documents ─────────────────────── */

function DocsTab({ reports, documents, user }) {
  return (
    <div className="space-y-6" data-testid="asset-docs">
      <div className="rounded-2xl border border-border bg-card p-6">
        <h2 className="font-semibold mb-4">Звіти SPV</h2>
        {reports.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="reports-empty">Звітів ще немає — перший з'явиться після звітного періоду.</p>
        ) : (
          <ul className="space-y-3" data-testid="asset-reports-list">
            {reports.map((r) => (
              <li key={r.id} className="flex items-start gap-3 p-3 rounded-xl border border-border bg-background/40">
                <FileText className="w-5 h-5 text-[#2E5D4F] shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-medium text-sm">{r.title}</p>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground">{r.report_type_label}{r.period_label ? ` · ${r.period_label}` : ''}</span>
                  </div>
                  {r.summary && <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{r.summary}</p>}
                </div>
                {r.download_url && (
                  <a href={`${process.env.REACT_APP_BACKEND_URL}${r.download_url}`} target="_blank" rel="noreferrer"
                     className="shrink-0 inline-flex items-center gap-1.5 px-3 h-8 rounded-full border border-border hover:border-[#2E5D4F] hover:text-[#2E5D4F] text-xs transition"
                     data-testid={`report-download-${r.id}`}>
                    <Download className="w-3.5 h-3.5" /> PDF
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-card p-6">
        <h2 className="font-semibold mb-4">Документи проєкту</h2>
        {documents.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="documents-empty">Документи ще не завантажені.</p>
        ) : (
          <ul className="space-y-2.5" data-testid="asset-documents-list">
            {documents.map((d) => (
              <li key={d.id} className="flex items-center gap-3 text-sm">
                {d.locked ? <Lock className="w-4 h-4 text-muted-foreground shrink-0" /> : <FileText className="w-4 h-4 text-[#2E5D4F] shrink-0" />}
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground shrink-0">{d.doc_type_label}</span>
                {d.locked ? (
                  <span className="text-muted-foreground" data-testid={`document-locked-${d.id}`}>
                    {d.title} <span className="text-xs">(доступно після входу)</span>
                  </span>
                ) : (
                  <a href={`${process.env.REACT_APP_BACKEND_URL}${d.download_url}`} target="_blank" rel="noreferrer" className="hover:underline" data-testid={`document-download-${d.id}`}>
                    {d.title}
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
        {!user && documents.some((d) => d.locked) && (
          <Link to="/auth" className="mt-4 inline-flex items-center gap-1.5 text-xs text-[#2E5D4F] hover:underline">
            <LogIn className="w-3.5 h-3.5" /> Увійдіть, щоб відкрити всі документи
          </Link>
        )}
      </div>
    </div>
  );
}

/* ────────────────────────────── Q&A ────────────────────────────── */

function QaTab({ assetId, questions, user, onAsked }) {
  const [question, setQuestion] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const ask = async () => {
    setError('');
    setSending(true);
    try {
      await lumen.post(`/investor/assets/${assetId}/questions`, { question });
      setQuestion('');
      setDone(true);
      setTimeout(() => setDone(false), 5000);
      onAsked?.();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось надіслати питання'));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="asset-qa">
      <div className="rounded-2xl border border-border bg-card p-6">
        <h2 className="font-semibold mb-1 flex items-center gap-2">
          <MessageCircleQuestion className="w-4 h-4 text-[#2E5D4F]" /> Поставити питання
        </h2>
        <p className="text-xs text-muted-foreground mb-3">Оператор відповідає публічно — відповідь побачать усі інвестори.</p>
        {user ? (
          <>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={3}
              placeholder="Наприклад: як захищені кошти інвесторів, якщо проєкт зупиниться?"
              className="w-full px-4 py-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm"
              data-testid="qa-question-input"
            />
            {error && <p className="mt-2 text-xs text-red-500" data-testid="qa-error">{String(error)}</p>}
            {done && (
              <p className="mt-2 text-xs text-emerald-700 flex items-center gap-1.5" data-testid="qa-success">
                <CheckCircle2 className="w-3.5 h-3.5" /> Питання надіслано — відповідь з'явиться тут.
              </p>
            )}
            <button
              onClick={ask}
              disabled={sending || question.trim().length < 10}
              className="mt-3 inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-40"
              data-testid="qa-submit"
            >
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <MessageCircleQuestion className="w-4 h-4" />}
              Надіслати питання
            </button>
          </>
        ) : (
          <Link to="/auth" className="inline-flex items-center gap-1.5 text-sm text-[#2E5D4F] hover:underline">
            <LogIn className="w-4 h-4" /> Увійдіть, щоб поставити питання
          </Link>
        )}
      </div>

      {questions.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground" data-testid="qa-empty">
          Ще немає жодного питання — будьте першим.
        </div>
      ) : (
        <div className="space-y-4" data-testid="qa-list">
          {questions.map((q) => (
            <div key={q.id} className="rounded-2xl border border-border bg-card p-5" data-testid={`qa-item-${q.id}`}>
              <div className="flex items-center gap-2 flex-wrap">
                <p className="font-medium text-sm">{q.investor_name}</p>
                {q.is_own && <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#2E5D4F]/10 text-[#2E5D4F] font-medium">ваше</span>}
                {q.status === 'pending' && <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-medium">очікує відповіді</span>}
                <span className="text-xs text-muted-foreground ml-auto">{formatDateUk(q.created_at)}</span>
              </div>
              <p className="mt-2 text-sm">{q.question}</p>
              {q.answer && (
                <div className="mt-3 p-3 rounded-xl bg-[#2E5D4F]/5 border border-[#2E5D4F]/15">
                  <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F] font-semibold mb-1">Відповідь оператора</p>
                  <p className="text-sm text-foreground/90 leading-relaxed">{q.answer}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────── shared bits ─────────────────────────── */

const Pill = ({ icon, label, value }) => (
  <div className="rounded-xl border border-border bg-card p-4">
    <div className="flex items-center gap-2 text-muted-foreground">{icon}<span className="text-[11px] uppercase tracking-widest">{label}</span></div>
    <p className="mt-2 font-semibold">{value}</p>
  </div>
);

const Row = ({ label, value }) => (
  <div className="flex justify-between">
    <span className="text-muted-foreground">{label}</span>
    <span className="font-medium">{value}</span>
  </div>
);

/* ════════════════════════════════════════════════════════════════════════════
   Економіка об'єкта — спільне джерело правди з мобайлом (без змін зі Sprint 2;
   статичні блоки ризиків/SPV винесено в динамічний контент активу — Sprint 5).
   ═══════════════════════════════════════════════════════════════════════════ */

function Economics({ assetId, amount }) {
  const [econ, setEcon] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scenario, setScenario] = useState('native');

  useEffect(() => {
    if (!assetId) return;
    let alive = true;
    setLoading(true);
    const ticket = Number(amount);
    const url = ticket && ticket > 0
      ? `/assets/${assetId}/economics?ticket=${ticket}`
      : `/assets/${assetId}/economics`;
    const t = setTimeout(() => {
      lumen.get(url)
        .then((r) => { if (alive) setEcon(r.data); })
        .catch(() => { if (alive) setEcon(null); })
        .finally(() => { if (alive) setLoading(false); });
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [assetId, amount]);

  if (loading && !econ) {
    return (
      <div className="rounded-2xl border border-border bg-card p-6">
        <div className="h-6 w-48 bg-muted animate-pulse rounded" />
        <div className="mt-3 h-4 w-72 bg-muted animate-pulse rounded" />
      </div>
    );
  }
  if (!econ) return null;

  // Сценарій «Що якби» — клієнтсько застосовує іншу категорію поверх серверних
  // даних. Збережена в SPV модель не змінюється — це чисто прев'ю.
  const econShown = applyScenario(econ, scenario);

  const rentalShare = econShown.shares?.rental ?? 0.55;
  const apprShare = econShown.shares?.appreciation ?? 0.45;
  const horizonY = econShown.horizon_years || 1;
  const annual = econShown.annual || {};
  const totals = econShown.totals || {};
  const rates = econShown.rates || {};

  return (
    <div className="rounded-2xl border border-border bg-card p-6 space-y-6" data-testid="asset-economics">
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F]">Економіка об'єкта</p>
          <h2 className="text-xl font-bold mt-1">Що ви реально заробите</h2>
        </div>
        <span className="text-[11px] text-muted-foreground">
          розрахунок на {formatUAH(econShown.ticket)} · {horizonY} р.
        </span>
      </header>

      {/* ─── Сценарії «Що якби» ─────────────────────────────────────────── */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
          Сценарій дохідності
        </p>
        <div className="flex flex-wrap gap-2">
          {ECONOMICS_SCENARIOS.map((sc) => {
            const active = scenario === sc.key;
            return (
              <button
                key={sc.key}
                type="button"
                data-testid={`scenario-${sc.key}`}
                onClick={() => setScenario(sc.key)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors border ${
                  active
                    ? 'bg-[#2E5D4F] text-white border-[#2E5D4F]'
                    : 'bg-background/40 border-border text-muted-foreground hover:bg-background/80'
                }`}
              >
                {sc.label}
              </button>
            );
          })}
        </div>
        <p className="text-[11px] text-muted-foreground mt-2">
          {scenario === 'native'
            ? 'Показано модель, збережену адміном для цього обʼєкта.'
            : 'Прев\'ю «що якби» — застосовано частки іншої категорії. Збережена в SPV модель не змінюється.'}
        </p>
      </div>

      <div className="grid sm:grid-cols-3 gap-3">
        <MetricCard icon={<Percent className="w-4 h-4" />}
          label="Чиста IRR" value={formatPercent(totals.net_irr_percent)}
          hint="після податків і комісій" tone="primary" />
        <MetricCard icon={<TrendingUp className="w-4 h-4" />}
          label="Брутто-дохідність" value={formatPercent(totals.gross_yield_percent)}
          hint="до податків" />
        <MetricCard icon={<Receipt className="w-4 h-4" />}
          label="Чистий грошовий потік" value={formatUAH(totals.total_net)}
          hint={`за ${horizonY} р.`} />
      </div>

      {/* Розподіл доходу */}
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Звідки приходить дохід</p>
        <div className="h-2.5 rounded-full overflow-hidden bg-muted flex">
          <div className="bg-[#2E5D4F]" style={{ width: `${rentalShare * 100}%` }} title="Оренда" />
          <div className="bg-[#C99B3D]" style={{ width: `${apprShare * 100}%` }} title="Переоцінка" />
        </div>
        <div className="mt-2 flex justify-between text-xs">
          <span className="text-[#2E5D4F]">● Оренда {Math.round(rentalShare * 100)}%</span>
          <span className="text-[#C99B3D]">● Переоцінка {Math.round(apprShare * 100)}%</span>
        </div>
      </div>

      {/* Витрати */}
      <div className="rounded-xl border border-border bg-background/40 p-4 space-y-1.5">
        <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Витрати, що зменшують ваш дохід (на рік)</p>
        <Row label="Орендні надходження (брутто)" value={formatUAH(annual.rental_gross)} />
        <Row label="Операційні витрати (комунальні, ремонт, страхування)" value={`− ${formatUAH(annual.opex)}`} />
        <Row label={`Податки (${Math.round((rates.tax_rate || 0) * 1000) / 10}%)`} value={`− ${formatUAH(annual.tax)}`} />
        <Row label={`Платформа Lumen (${Math.round((rates.platform_fee || 0) * 1000) / 10}%)`} value={`− ${formatUAH(annual.platform_fee)}`} />
        <div className="pt-2 mt-2 border-t border-border flex justify-between font-semibold">
          <span>Чистий дохід на руки (рік)</span>
          <span className="text-[#2E5D4F]">{formatUAH(annual.rental_net)}</span>
        </div>
      </div>

      {/* Cashflow */}
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Грошовий потік по роках</p>
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-widest text-muted-foreground">
                <th className="text-left px-2 py-2 font-medium">Рік</th>
                <th className="text-right px-2 py-2 font-medium">Оренда (net)</th>
                <th className="text-right px-2 py-2 font-medium">Вихід / переоцінка</th>
                <th className="text-right px-2 py-2 font-medium">Підсумок</th>
              </tr>
            </thead>
            <tbody>
              {(econShown.cashflow || []).map((r) => (
                <tr key={r.year} className="border-t border-border">
                  <td className="px-2 py-2">Рік {r.year}</td>
                  <td className="px-2 py-2 text-right">{formatUAH(r.rental_net)}</td>
                  <td className="px-2 py-2 text-right text-[#C99B3D]">{r.exit ? formatUAH(r.exit) : '—'}</td>
                  <td className="px-2 py-2 text-right font-semibold">{formatUAH(r.total)}</td>
                </tr>
              ))}
              <tr className="border-t-2 border-foreground/30 bg-background/40">
                <td className="px-2 py-2 font-semibold">Сума</td>
                <td className="px-2 py-2 text-right font-semibold">{formatUAH((annual.rental_net || 0) * horizonY)}</td>
                <td className="px-2 py-2 text-right font-semibold text-[#C99B3D]">{formatUAH(econShown.exit?.appreciation_net)}</td>
                <td className="px-2 py-2 text-right font-bold text-[#2E5D4F]">{formatUAH(totals.total_net)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground leading-relaxed">
        Розрахунки прогнозні і не є офертою. Фактичні показники залежать від орендаря, ринку та операційних витрат.
        Перед інвестуванням ознайомтесь із документами проєкту у вкладці «Звіти й документи».
      </p>
    </div>
  );
}

const MetricCard = ({ icon, label, value, hint, tone }) => (
  <div className={`rounded-xl border p-4 ${tone === 'primary' ? 'border-[#2E5D4F]/40 bg-[#2E5D4F]/5' : 'border-border bg-background/40'}`}>
    <div className="flex items-center gap-2 text-muted-foreground">{icon}
      <span className="text-[10px] uppercase tracking-widest">{label}</span>
    </div>
    <p className={`mt-2 text-xl font-bold ${tone === 'primary' ? 'text-[#2E5D4F]' : ''}`}>{value}</p>
    {hint && <p className="text-[10px] text-muted-foreground mt-1">{hint}</p>}
  </div>
);
