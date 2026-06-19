import { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ArrowRight, MapPin, ShieldCheck, Building2, TrendingUp,
  Calendar, Users, FileText, Newspaper, HelpCircle, ExternalLink,
  CheckCircle2, Image as ImageIcon, Layers, Gauge,
} from 'lucide-react';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import { useAuth } from '@/App';
import { lumen, formatUAH, formatPercent, formatDateUk } from '@/lib/lumenApi';
import {
  useAssetIntelligence, IntelligencePanel, InvestmentThesis, ScenarioEngine,
  CapitalStack, AssetJournal, SimilarAssets,
  AssetSnapshot, WhyWeInvested, CashFlow, RoundsTimeline,
} from '@/components/lumen/AssetIntelligence';
import AssetCommunity from '@/components/lumen/AssetCommunity';
import AssetLiquidity from '@/components/lumen/AssetLiquidity';
import AssetMap from '@/components/public/AssetMap';
import { trackEvent } from '@/lib/activityTracker';
import './LandingPage.css';

const dashFor = (user) => (user?.role === 'admin' ? '/admin/dashboard' : '/investor/dashboard');

export default function PublicAssetDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [dto, setDto] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('overview');
  const { intel, journal, similar } = useAssetIntelligence(dto?.asset_id);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    lumen.get(`/public/marketplace/${id}`)
      .then((r) => { if (alive) { setDto(r.data); document.title = `${r.data?.hero?.title || 'Об\u0027єкт'} · Lumen`; try { trackEvent('asset_view', { asset_id: r.data?.asset_id || id, surface: 'public', title: r.data?.hero?.title }); } catch (_) {} } })
      .catch(() => { if (alive) setError('Об\u0027єкт не знайдено'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id]);

  const goInvest = () => {
    if (user) navigate('/investor/opportunities');
    else navigate('/auth?mode=register');
  };

  return (
    <div className="min-h-screen bg-background text-foreground lumen-landing">
      <TopBar user={user} />
      {loading && <CenterMsg>Завантаження…</CenterMsg>}
      {!loading && error && (
        <CenterMsg>
          {error} · <Link to="/" className="text-[#2E5D4F] underline ml-1">На головну</Link>
        </CenterMsg>
      )}
      {!loading && dto && (
        <>
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pt-6">
            <Link to="/#assets" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition" data-testid="public-back-link">
              <ArrowLeft className="w-4 h-4" /> Усі об'єкти
            </Link>
          </div>

          <Hero hero={dto.hero} action={dto.action} />

          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pb-24 grid lg:grid-cols-[1fr_360px] gap-8 mt-8">
            {/* MAIN */}
            <div className="min-w-0">
              <TrustBar trust={dto.trust} />

              <Tabs tab={tab} setTab={setTab} dto={dto} journalCount={journal?.length || 0} />

              {tab === 'overview' && <OverviewSection dto={dto} intel={intel} similar={similar} />}
              {tab === 'liquidity' && <AssetLiquidity assetId={dto.asset_id} user={user} />}
              {tab === 'community' && <AssetCommunity assetId={dto.asset_id} user={user} basePath="objects" />}
              {tab === 'journal' && <AssetJournal items={journal} />}
              {tab === 'gallery' && <GallerySection gallery={dto.sections?.gallery} />}
              {tab === 'updates' && <UpdatesSection updates={dto.sections?.updates} reports={dto.sections?.reports} />}
              {tab === 'qa' && <QASection qa={dto.sections?.qa} />}
            </div>

            {/* STICKY ACTION CARD */}
            <div className="lg:sticky lg:top-6 self-start">
              <ActionCard action={dto.action} trust={dto.trust} listing={dto.listing} user={user} onInvest={goInvest} />
            </div>
          </div>
          <FooterMini />
        </>
      )}
    </div>
  );
}

const CenterMsg = ({ children }) => (
  <div className="mx-auto max-w-7xl px-4 py-32 text-center text-muted-foreground" data-testid="public-detail-msg">{children}</div>
);

const TopBar = ({ user }) => (
  <header className="sticky top-0 z-30 backdrop-blur-xl bg-background/80 border-b border-border">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <Link to="/" className="flex items-center"><Logo height={32} /></Link>
      <div className="flex items-center gap-2">
        <ThemeToggle />
        {user ? (
          <Link to={dashFor(user)} className="lumen-btn-primary text-sm font-medium px-4 h-9" data-testid="public-cabinet-btn">
            Мій кабінет
          </Link>
        ) : (
          <>
            <Link to="/auth" className="hidden sm:inline-flex text-sm font-medium text-muted-foreground hover:text-foreground transition px-3 h-9 items-center">Увійти</Link>
            <Link to="/auth?mode=register" className="lumen-btn-primary text-sm font-medium px-4 h-9">Стати інвестором</Link>
          </>
        )}
      </div>
    </div>
  </header>
);

const Hero = ({ hero, action }) => (
  <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 mt-4">
    <div className="relative rounded-3xl overflow-hidden border border-border min-h-[320px] flex items-end" data-testid="public-hero"
      style={hero?.cover_url ? { backgroundImage: `linear-gradient(to top, rgba(0,0,0,0.78), rgba(0,0,0,0.15)), url(${hero.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : { background: 'var(--muted)' }}
    >
      <div className="p-6 sm:p-10 text-white w-full">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <span className="px-2.5 py-1 text-[10px] uppercase tracking-widest rounded-full bg-white/15 backdrop-blur border border-white/25 font-semibold">
            {hero?.category_label || hero?.category}
          </span>
          {hero?.status === 'open' && (
            <span className="px-2.5 py-1 text-[10px] uppercase tracking-widest rounded-full bg-emerald-500 text-white font-semibold flex items-center gap-1">
              <span className="w-1 h-1 rounded-full bg-white animate-pulse" /> {hero?.status_label || 'відкрито'}
            </span>
          )}
        </div>
        <h1 className="text-3xl sm:text-5xl font-bold leading-tight max-w-3xl">{hero?.title}</h1>
        {hero?.location && (
          <p className="mt-3 flex items-center gap-1.5 text-white/85"><MapPin className="w-4 h-4" /> {hero.location}</p>
        )}
        <div className="mt-5 flex items-center gap-6 flex-wrap">
          <HeroStat label="Цільова дохідність" value={formatPercent(action?.target_yield)} accent />
          <HeroStat label="Мін. внесок" value={formatUAH(action?.min_ticket)} />
          <HeroStat label="Зібрано" value={`${action?.progress_percent || 0}%`} />
        </div>
      </div>
    </div>
  </section>
);

const HeroStat = ({ label, value, accent }) => (
  <div>
    <p className="text-[10px] uppercase tracking-widest text-white/65">{label}</p>
    <p className={`text-xl font-bold ${accent ? 'text-[#D9C089]' : 'text-white'}`}>{value}</p>
  </div>
);

const TrustBar = ({ trust }) => (
  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6" data-testid="public-trust">
    <TrustCell icon={<ShieldCheck className="w-4 h-4" />} label="SPV" value={trust?.spv_label || '—'} />
    <TrustCell icon={<TrendingUp className="w-4 h-4" />} label="Дохідність" value={formatPercent(trust?.target_yield)} />
    <TrustCell icon={<Calendar className="w-4 h-4" />} label="Горизонт" value={trust?.horizon_label || '—'} />
    <TrustCell icon={<Users className="w-4 h-4" />} label="Інвесторів" value={trust?.investors_count ?? 0} />
  </div>
);

const TrustCell = ({ icon, label, value }) => (
  <div className="rounded-xl border border-border bg-card p-3">
    <div className="flex items-center gap-1.5 text-muted-foreground text-[10px] uppercase tracking-widest">{icon}{label}</div>
    <p className="mt-1 text-sm font-semibold truncate" title={String(value)}>{value}</p>
  </div>
);

const Tabs = ({ tab, setTab, dto, journalCount = 0 }) => {
  const items = [
    { k: 'overview', label: 'Огляд', icon: Layers },
    { k: 'liquidity', label: 'Ліквідність', icon: Gauge },
    { k: 'community', label: 'Спільнота', icon: Users },
    { k: 'journal', label: 'Шлях активу', icon: Calendar, count: journalCount },
    { k: 'gallery', label: 'Галерея', icon: ImageIcon, count: (dto.sections?.gallery?.photos?.length || 0) },
    { k: 'updates', label: 'Оновлення та звіти', icon: Newspaper, count: ((dto.sections?.updates?.length || 0) + (dto.sections?.reports?.length || 0)) },
    { k: 'qa', label: 'Питання', icon: HelpCircle, count: (dto.sections?.qa?.count || 0) },
  ];
  return (
    <div className="flex items-center gap-1 border-b border-border mb-6 overflow-x-auto" data-testid="public-tabs">
      {items.map((it) => {
        const Icon = it.icon;
        const active = tab === it.k;
        return (
          <button key={it.k} onClick={() => setTab(it.k)} data-testid={`public-tab-${it.k}`}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition ${active ? 'border-[#2E5D4F] text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
            <Icon className="w-4 h-4" /> {it.label}
            {it.count ? <span className="ml-0.5 text-xs text-muted-foreground">· {it.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
};

const OverviewSection = ({ dto, intel, similar }) => {
  const hero = dto.hero || {};
  const map = dto.sections?.map;
  return (
    <div className="space-y-8" data-testid="public-overview">
      {intel?.snapshot && <AssetSnapshot snapshot={intel.snapshot} />}
      {intel?.highlights?.length > 0 && <WhyWeInvested highlights={intel.highlights} />}
      {intel && (
        <IntelligencePanel metrics={intel.metrics} conviction={intel.conviction} liquidity={intel.liquidity} />
      )}
      {intel?.cashflow && <CashFlow data={intel.cashflow} />}
      {intel?.rounds && <RoundsTimeline data={intel.rounds} />}
      {hero.description && (
        <Block title="Про об'єкт">
          <p className="text-[15px] leading-relaxed text-muted-foreground whitespace-pre-line">{hero.description}</p>
        </Block>
      )}
      {intel?.thesis && <InvestmentThesis thesis={intel.thesis} />}
      {intel?.scenarios && <ScenarioEngine data={intel.scenarios} />}
      {intel?.capital_stack && <CapitalStack data={intel.capital_stack} />}
      {map && (map.lat || map.region) && (
        <Block title="Розташування">
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground"><MapPin className="w-4 h-4" /> {map.address || map.region}{map.district ? `, ${map.district}` : ''}</p>
          {Array.isArray(map.infrastructure) && map.infrastructure.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {map.infrastructure.map((x, i) => (
                <span key={i} className="px-2.5 py-1 rounded-full text-xs bg-muted border border-border">{x}</span>
              ))}
            </div>
          )}
          <AssetMap lat={map.lat} lng={map.lng} label={hero.title} address={map.address || map.region} />
        </Block>
      )}
      {dto.action && (
        <Block title="Економіка раунду">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <KV label="Ціль раунду" value={formatUAH(dto.action.round_target)} />
            <KV label="Зібрано" value={formatUAH(dto.action.raised)} />
            <KV label="Прогрес" value={`${dto.action.progress_percent || 0}%`} />
            <KV label="Дедлайн" value={dto.action.round_deadline ? formatDateUk(dto.action.round_deadline) : '—'} />
          </div>
        </Block>
      )}
      <SimilarAssets items={similar} basePath="/objects" />
    </div>
  );
};

const GallerySection = ({ gallery }) => {
  const photos = gallery?.photos || [];
  if (!photos.length) return <Empty>Галерея порожня</Empty>;
  return (
    <div className="grid sm:grid-cols-2 gap-4" data-testid="public-gallery">
      {photos.map((p, i) => (
        <figure key={i} className="rounded-xl overflow-hidden border border-border bg-card">
          <img src={p.url || p} alt={p.caption || `Фото ${i + 1}`} className="w-full h-56 object-cover" loading="lazy" />
          {p.caption && <figcaption className="px-3 py-2 text-xs text-muted-foreground">{p.caption}</figcaption>}
        </figure>
      ))}
    </div>
  );
};

const UpdatesSection = ({ updates, reports }) => {
  const u = updates || []; const r = reports || [];
  if (!u.length && !r.length) return <Empty>Поки немає оновлень та звітів</Empty>;
  return (
    <div className="space-y-8" data-testid="public-updates">
      {u.length > 0 && (
        <Block title="Оновлення">
          <div className="space-y-4">
            {u.map((up, i) => (
              <div key={up.id || i} className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-center justify-between gap-3">
                  <h4 className="font-semibold">{up.title}</h4>
                  {up.created_at && <span className="text-xs text-muted-foreground">{formatDateUk(up.created_at)}</span>}
                </div>
                {up.body && <p className="mt-2 text-sm text-muted-foreground whitespace-pre-line">{up.body}</p>}
              </div>
            ))}
          </div>
        </Block>
      )}
      {r.length > 0 && (
        <Block title="Звіти">
          <div className="space-y-2">
            {r.map((rep, i) => (
              <div key={rep.id || i} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                  <span className="text-sm truncate">{rep.title || rep.period || 'Звіт'}</span>
                </div>
                {rep.created_at && <span className="text-xs text-muted-foreground shrink-0">{formatDateUk(rep.created_at)}</span>}
              </div>
            ))}
          </div>
        </Block>
      )}
    </div>
  );
};

const QASection = ({ qa }) => {
  const items = qa?.items || [];
  if (!items.length) return <Empty>Поки немає відповідей на питання</Empty>;
  return (
    <div className="space-y-4" data-testid="public-qa">
      {items.map((q, i) => (
        <div key={q.id || i} className="rounded-xl border border-border bg-card p-4">
          <p className="font-medium flex items-start gap-2"><HelpCircle className="w-4 h-4 mt-0.5 text-[#2E5D4F] shrink-0" /> {q.question}</p>
          {q.answer && (
            <div className="mt-2 ml-6 pl-3 border-l-2 border-[#2E5D4F]/40">
              <p className="text-sm text-muted-foreground whitespace-pre-line">{q.answer}</p>
              <p className="mt-1 text-[11px] text-muted-foreground/70">Відповідь оператора{q.answered_at ? ` · ${formatDateUk(q.answered_at)}` : ''}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

const ActionCard = ({ action, trust, listing, user, onInvest }) => (
  <div className="rounded-2xl border border-border bg-card p-6 shadow-sm" data-testid="public-action-card">
    <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Цільова дохідність</p>
    <p className="text-4xl font-bold text-[#2E5D4F]">{formatPercent(action?.target_yield)}</p>
    <p className="mt-1 text-sm text-muted-foreground">на рік · горизонт {trust?.horizon_label || '—'}</p>

    <div className="mt-5 space-y-3">
      <KV label="Мінімальний внесок" value={formatUAH(action?.min_ticket)} />
      <KV label="Ціль раунду" value={formatUAH(action?.round_target)} />
      <KV label="Зібрано" value={`${formatUAH(action?.raised)} · ${action?.progress_percent || 0}%`} />
      {action?.round_deadline && <KV label="Дедлайн раунду" value={formatDateUk(action.round_deadline)} />}
    </div>

    <div className="mt-4 h-1.5 rounded-full bg-muted overflow-hidden">
      <div className="h-full bg-gradient-to-r from-[#C9A961] to-[#A98A45]" style={{ width: `${action?.progress_percent || 0}%` }} />
    </div>

    {listing && listing.price_per_unit && (
      <div className="mt-5 rounded-xl border border-[#2E5D4F]/25 bg-[#2E5D4F]/5 p-3">
        <p className="text-xs font-semibold text-[#2E5D4F] uppercase tracking-wide">Вторинний ринок</p>
        <p className="mt-1 text-sm">Доступна частка від {listing.seller_label || 'інвестора'} за ціною {Number(listing.price_per_unit).toFixed(3)}×</p>
      </div>
    )}

    <button onClick={onInvest} className="lumen-btn-primary w-full mt-6 h-11 justify-center group" data-testid="public-invest-btn">
      {user ? 'Інвестувати в об\u0027єкт' : 'Стати інвестором'} <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
    </button>
    <div className="mt-3 flex items-start gap-2 text-[11px] text-muted-foreground">
      <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 text-emerald-500 shrink-0" />
      <span>Резиденти України · окрема SPV · щомісячна звітність</span>
    </div>
  </div>
);

const Block = ({ title, children }) => (
  <section>
    <h3 className="text-lg font-semibold mb-3">{title}</h3>
    {children}
  </section>
);

const KV = ({ label, value }) => (
  <div className="flex items-center justify-between gap-3">
    <span className="text-sm text-muted-foreground">{label}</span>
    <span className="text-sm font-semibold text-right">{value}</span>
  </div>
);

const Empty = ({ children }) => (
  <div className="rounded-xl border border-dashed border-border p-10 text-center text-muted-foreground text-sm">{children}</div>
);

const FooterMini = () => (
  <footer className="border-t border-border py-10">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex items-center justify-between flex-wrap gap-4">
      <Logo height={26} />
      <p className="text-xs text-muted-foreground">© Lumen · Колективні інвестиції в реальні активи в Україні</p>
      <Link to="/#assets" className="text-sm text-[#2E5D4F] hover:underline inline-flex items-center gap-1">Усі об'єкти <ArrowRight className="w-3.5 h-3.5" /></Link>
    </div>
  </footer>
);
