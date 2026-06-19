import { useEffect, useState, useCallback } from 'react';
import { lumen, formatDateUk } from '@/lib/lumenApi';
import {
  Users, MessageSquare, Megaphone, Lock, ThumbsUp, Lightbulb, AlertTriangle,
  Vote, Trophy, Send, Smile, Meh, Frown, ShieldCheck, CornerDownRight,
  HelpCircle, Sparkles, ChevronDown, ChevronUp, Pin, BadgeCheck,
} from 'lucide-react';

const PRIMARY = '#2E5D4F';

const REP_TONE = {
  leader: 'bg-amber-100 text-amber-800 border-amber-200',
  active: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  member: 'bg-sky-100 text-sky-700 border-sky-200',
  observer: 'bg-muted text-muted-foreground border-border',
};
const REACTION_META = {
  like: { icon: ThumbsUp, label: 'Підтримую' },
  insightful: { icon: Lightbulb, label: 'Корисно' },
  concern: { icon: AlertTriangle, label: 'Занепокоєння' },
};
const MOODS = [
  { key: 'positive', icon: Smile, label: 'Задоволений', color: 'text-emerald-600', ring: 'data-[on=true]:bg-emerald-50 data-[on=true]:border-emerald-300' },
  { key: 'neutral', icon: Meh, label: 'Нейтрально', color: 'text-amber-600', ring: 'data-[on=true]:bg-amber-50 data-[on=true]:border-amber-300' },
  { key: 'negative', icon: Frown, label: 'Занепокоєний', color: 'text-rose-600', ring: 'data-[on=true]:bg-rose-50 data-[on=true]:border-rose-300' },
];

const initials = (n) => (n || 'I').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();

function RepChip({ rep }) {
  if (!rep) return null;
  return <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${REP_TONE[rep.tier] || REP_TONE.observer}`}>{rep.tier_label}</span>;
}

/* ════════════════════ Sentiment + header ════════════════════ */

function SentimentBar({ s }) {
  if (!s) return null;
  const seg = [
    { v: s.positive || 0, c: '#10b981', l: 'задоволені' },
    { v: s.neutral || 0, c: '#f59e0b', l: 'нейтральні' },
    { v: s.negative || 0, c: '#f43f5e', l: 'занепокоєні' },
  ];
  return (
    <div data-testid="asset-sentiment">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Настрій інвесторів</span>
        <span className="text-xs font-medium">{s.available ? s.label : 'Ще немає оцінок'}</span>
      </div>
      <div className="h-2.5 rounded-full overflow-hidden flex bg-muted">
        {s.available && seg.map((g, i) => g.v > 0 && <div key={i} style={{ width: `${g.v}%`, backgroundColor: g.c }} title={`${g.v}% ${g.l}`} />)}
      </div>
      {s.available && (
        <div className="mt-1.5 flex gap-3 text-[11px] text-muted-foreground">
          {seg.map((g, i) => <span key={i} className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: g.c }} />{g.v}%</span>)}
          <span className="ml-auto">{s.voters} голос(ів)</span>
        </div>
      )}
    </div>
  );
}

/* ════════════════════ Post card ════════════════════ */

function PostCard({ post, canInteract, onChanged }) {
  const [open, setOpen] = useState(false);
  const [comments, setComments] = useState(null);
  const [text, setText] = useState('');
  const [p, setP] = useState(post);
  useEffect(() => setP(post), [post]);

  const loadComments = useCallback(async () => {
    try {
      const r = await lumen.get(`/community/posts/${p.id}`);
      setComments(r.data.comments || []);
      setP(r.data.post);
    } catch (_) { setComments([]); }
  }, [p.id]);

  const toggleOpen = () => { const n = !open; setOpen(n); if (n && comments === null) loadComments(); };

  const react = async (reaction) => {
    if (!canInteract) return;
    try { const r = await lumen.post(`/community/posts/${p.id}/react`, { reaction }); setP(r.data.post); } catch (_) {}
  };
  const submitComment = async () => {
    if (text.trim().length < 2) return;
    try { await lumen.post(`/community/posts/${p.id}/comments`, { body: text }); setText(''); await loadComments(); onChanged && onChanged(); }
    catch (e) { alert(e?.response?.data?.detail || 'Помилка'); }
  };

  const KindIcon = p.kind === 'announcement' ? Megaphone : p.kind === 'question' ? HelpCircle : MessageSquare;
  const kindLabel = p.kind === 'announcement' ? 'Оголошення' : p.kind === 'question' ? 'Питання' : 'Обговорення';

  return (
    <div className={`rounded-xl border p-4 ${p.is_operator ? 'border-[#2E5D4F]/30 bg-[#2E5D4F]/[0.04]' : 'border-border bg-card'}`} data-testid={`post-${p.id}`}>
      <div className="flex items-start gap-3">
        <div className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 ${p.is_operator ? 'bg-[#2E5D4F] text-white' : 'bg-muted'}`}>
          {p.is_operator ? <ShieldCheck className="w-4 h-4" /> : initials(p.author_name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm">{p.author_name}</span>
            {p.is_operator && <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-[#2E5D4F] text-white"><BadgeCheck className="w-3 h-3" />Оператор</span>}
            <RepChip rep={p.author_rep} />
            <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground"><KindIcon className="w-3 h-3" />{kindLabel}</span>
            {p.pinned && <Pin className="w-3 h-3 text-[#C99B3D]" />}
            {p.visibility === 'holders' && <Lock className="w-3 h-3 text-muted-foreground" title="Тільки для власників" />}
            <span className="text-[11px] text-muted-foreground ml-auto">{formatDateUk(p.created_at)}</span>
          </div>
          {p.title && <h4 className="mt-1.5 font-semibold text-[15px]">{p.title}</h4>}
          {p.body && <p className="mt-1 text-sm text-muted-foreground leading-relaxed whitespace-pre-line">{p.body}</p>}

          {p.answer && (
            <div className="mt-3 rounded-lg border border-[#2E5D4F]/30 bg-[#2E5D4F]/[0.05] p-3">
              <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F] flex items-center gap-1"><ShieldCheck className="w-3 h-3" />Відповідь оператора</p>
              <p className="mt-1 text-sm leading-relaxed">{p.answer}</p>
            </div>
          )}

          <div className="mt-3 flex items-center gap-1 flex-wrap">
            {Object.entries(REACTION_META).map(([key, meta]) => {
              const Icon = meta.icon;
              const count = p.reaction_counts?.[key] || 0;
              const on = (p.my_reactions || []).includes(key);
              return (
                <button key={key} onClick={() => react(key)} disabled={!canInteract} data-testid={`react-${key}-${p.id}`}
                  className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border transition ${on ? 'border-[#2E5D4F] bg-[#2E5D4F]/10 text-[#2E5D4F]' : 'border-border text-muted-foreground hover:border-[#2E5D4F]/40'} ${!canInteract ? 'opacity-60 cursor-default' : ''}`}>
                  <Icon className="w-3.5 h-3.5" />{count > 0 && count}
                </button>
              );
            })}
            <button onClick={toggleOpen} data-testid={`comments-toggle-${p.id}`}
              className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border border-border text-muted-foreground hover:border-[#2E5D4F]/40 ml-1">
              <MessageSquare className="w-3.5 h-3.5" />{p.comment_count || 0}{open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          </div>

          {open && (
            <div className="mt-3 space-y-3 border-t border-border pt-3" data-testid={`comments-${p.id}`}>
              {comments === null ? <p className="text-xs text-muted-foreground">Завантаження…</p> :
                comments.length === 0 ? <p className="text-xs text-muted-foreground">Ще немає коментарів.</p> :
                comments.map((c) => (
                  <div key={c.id} className="flex items-start gap-2">
                    <CornerDownRight className="w-3.5 h-3.5 text-muted-foreground mt-1 shrink-0" />
                    <div className={`flex-1 rounded-lg p-2.5 ${c.is_operator ? 'bg-[#2E5D4F]/[0.05] border border-[#2E5D4F]/20' : 'bg-muted/50'}`}>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium">{c.author_name}</span>
                        {c.is_operator && <span className="text-[9px] px-1 py-0.5 rounded bg-[#2E5D4F] text-white">Оператор</span>}
                        <span className="text-[10px] text-muted-foreground ml-auto">{formatDateUk(c.created_at)}</span>
                      </div>
                      <p className="text-sm mt-0.5">{c.body}</p>
                    </div>
                  </div>
                ))}
              {canInteract && (
                <div className="flex items-center gap-2">
                  <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Додати коментар…" data-testid={`comment-input-${p.id}`}
                    onKeyDown={(e) => e.key === 'Enter' && submitComment()}
                    className="flex-1 h-9 px-3 rounded-lg border border-border bg-background text-sm focus:outline-none focus:border-[#2E5D4F]" />
                  <button onClick={submitComment} data-testid={`comment-send-${p.id}`} className="h-9 px-3 rounded-lg bg-[#2E5D4F] text-white"><Send className="w-4 h-4" /></button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ════════════════════ Poll card (C4) ════════════════════ */

function PollCard({ poll, canVote, onVoted }) {
  const [p, setP] = useState(poll);
  useEffect(() => setP(poll), [poll]);
  const vote = async (option_key) => {
    if (!canVote || p.status !== 'open') return;
    try { const r = await lumen.post(`/community/polls/${p.id}/vote`, { option_key }); setP(r.data.poll); onVoted && onVoted(); }
    catch (e) { alert(e?.response?.data?.detail || 'Помилка голосування'); }
  };
  return (
    <div className="rounded-xl border border-border bg-card p-4" data-testid={`poll-${p.id}`}>
      <div className="flex items-center gap-2">
        <Vote className="w-4 h-4 text-[#2E5D4F]" />
        <h4 className="font-semibold text-sm">{p.question}</h4>
        <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full ${p.status === 'open' ? 'bg-emerald-100 text-emerald-700' : 'bg-muted text-muted-foreground'}`}>{p.status === 'open' ? 'відкрите' : 'закрите'}</span>
      </div>
      <p className="text-[11px] text-muted-foreground mt-1">Вага голосу = ваші units · рекомендаційне</p>
      <div className="mt-3 space-y-2">
        {p.options.map((o) => {
          const mine = p.my_vote === o.key;
          return (
            <button key={o.key} onClick={() => vote(o.key)} disabled={!canVote || p.status !== 'open'} data-testid={`vote-${o.key}-${p.id}`}
              className={`w-full text-left rounded-lg border p-2.5 relative overflow-hidden transition ${mine ? 'border-[#2E5D4F]' : 'border-border'} ${canVote && p.status === 'open' ? 'hover:border-[#2E5D4F]/50' : 'cursor-default'}`}>
              <div className="absolute inset-0 bg-[#2E5D4F]/10" style={{ width: `${o.percent}%` }} />
              <div className="relative flex items-center justify-between text-sm">
                <span className="flex items-center gap-2">{mine && <BadgeCheck className="w-4 h-4 text-[#2E5D4F]" />}{o.label}</span>
                <span className="font-medium">{o.percent}%</span>
              </div>
            </button>
          );
        })}
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground flex justify-between">
        <span>{p.total_voters} голос(ів) · {Number(p.total_units).toLocaleString('uk-UA')} units</span>
        {p.my_vote && <span className="text-[#2E5D4F]">ви проголосували</span>}
      </div>
    </div>
  );
}

/* ════════════════════ Composer ════════════════════ */

function Composer({ assetId, kind, isHolder, onPosted }) {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (body.trim().length < 5) return;
    setBusy(true);
    try {
      await lumen.post(`/assets/${assetId}/community/posts`, { kind, title, body });
      setTitle(''); setBody(''); onPosted && onPosted();
    } catch (e) { alert(e?.response?.data?.detail || 'Помилка'); }
    finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl border border-border bg-card p-4" data-testid={`composer-${kind}`}>
      {kind === 'discussion' && (
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Тема обговорення" data-testid="composer-title"
          className="w-full h-10 px-3 mb-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:border-[#2E5D4F]" />
      )}
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3}
        placeholder={kind === 'question' ? 'Поставте питання оператору…' : 'Поділіться думкою зі співвласниками…'} data-testid="composer-body"
        className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:border-[#2E5D4F]" />
      <div className="flex items-center justify-between mt-2">
        <span className="text-[11px] text-muted-foreground">{kind === 'question' ? 'Питання побачать усі' : 'Видно лише власникам часток'}</span>
        <button onClick={submit} disabled={busy} data-testid="composer-submit"
          className="inline-flex items-center gap-2 px-4 h-9 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 disabled:opacity-60">
          <Send className="w-4 h-4" />{kind === 'question' ? 'Запитати' : 'Опублікувати'}
        </button>
      </div>
    </div>
  );
}

/* ════════════════════ Main community component ════════════════════ */

export default function AssetCommunity({ assetId, user, basePath = 'investor' }) {
  const [summary, setSummary] = useState(null);
  const [feed, setFeed] = useState([]);
  const [polls, setPolls] = useState([]);
  const [leaders, setLeaders] = useState([]);
  const [section, setSection] = useState('feed');
  const [loading, setLoading] = useState(true);

  const isAuthed = !!user;
  const isHolder = !!summary?.is_holder;

  const load = useCallback(async () => {
    if (!assetId) return;
    try {
      const [s, f, p, l] = await Promise.all([
        lumen.get(`/assets/${assetId}/community/summary`).catch(() => null),
        lumen.get(`/assets/${assetId}/community/feed`).catch(() => null),
        lumen.get(`/assets/${assetId}/community/polls`).catch(() => null),
        lumen.get(`/assets/${assetId}/community/leaderboard`).catch(() => null),
      ]);
      setSummary(s?.data || null);
      setFeed(f?.data?.items || []);
      setPolls(p?.data?.items || []);
      setLeaders(l?.data?.items || []);
    } finally { setLoading(false); }
  }, [assetId]);

  useEffect(() => { load(); }, [load]);

  const setMood = async (mood) => {
    if (!isHolder) return;
    try { const r = await lumen.post(`/assets/${assetId}/community/sentiment`, { mood }); setSummary((s) => ({ ...s, my_sentiment: r.data.my_sentiment, sentiment: r.data.sentiment })); } catch (_) {}
  };

  if (loading) return <div className="h-48 rounded-2xl bg-muted/40 animate-pulse" />;

  const lounge = feed.filter((p) => p.kind === 'discussion');
  const stream = feed.filter((p) => p.kind !== 'discussion');
  const openPolls = polls.filter((p) => p.status === 'open');

  const SECTIONS = [
    { k: 'feed', label: 'Стрічка', icon: Megaphone, count: stream.length },
    { k: 'lounge', label: 'Lounge', icon: isHolder ? MessageSquare : Lock, count: lounge.length },
    { k: 'polls', label: 'Голосування', icon: Vote, count: openPolls.length },
    { k: 'leaders', label: 'Рейтинг', icon: Trophy, count: leaders.length },
  ];

  return (
    <div className="space-y-5" data-testid="asset-community">
      {/* Header */}
      <div className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-4 h-4 text-[#2E5D4F]" />
          <h2 className="font-semibold">Спільнота власників</h2>
          <span className="text-[11px] text-muted-foreground ml-auto flex items-center gap-1"><Users className="w-3.5 h-3.5" />{summary?.holders_count || 0} власників</span>
        </div>
        <SentimentBar s={summary?.sentiment} />
        {isHolder ? (
          <div className="mt-4 flex items-center gap-2 flex-wrap" data-testid="mood-selector">
            <span className="text-xs text-muted-foreground mr-1">Ваша оцінка об'єкта:</span>
            {MOODS.map(({ key, icon: Icon, label, color, ring }) => (
              <button key={key} onClick={() => setMood(key)} data-on={summary?.my_sentiment === key} data-testid={`mood-${key}`}
                className={`inline-flex items-center gap-1.5 px-3 h-8 rounded-full border border-border text-xs transition ${ring}`}>
                <Icon className={`w-4 h-4 ${color}`} />{label}
              </button>
            ))}
            {summary?.my_reputation && (
              <span className="ml-auto inline-flex items-center gap-1 text-[11px]"><Trophy className="w-3.5 h-3.5 text-[#C99B3D]" /><RepChip rep={summary.my_reputation} /></span>
            )}
          </div>
        ) : isAuthed ? (
          <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground rounded-lg border border-dashed border-border p-3">
            <Lock className="w-4 h-4" /> Придбайте частку, щоб брати участь у lounge, голосуваннях та оцінці настрою.
          </div>
        ) : (
          <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground rounded-lg border border-dashed border-border p-3">
            <Lock className="w-4 h-4" /> Увійдіть, щоб ставити питання та приєднатися до спільноти.
          </div>
        )}
      </div>

      {/* Sub-nav */}
      <div className="flex gap-2 flex-wrap">
        {SECTIONS.map(({ k, label, icon: Icon, count }) => (
          <button key={k} onClick={() => setSection(k)} data-testid={`community-tab-${k}`}
            className={`inline-flex items-center gap-1.5 px-3 h-9 rounded-full text-sm border transition ${section === k ? 'bg-[#2E5D4F] text-white border-[#2E5D4F]' : 'border-border text-muted-foreground hover:border-[#2E5D4F]/40'}`}>
            <Icon className="w-4 h-4" />{label}{count > 0 && <span className="text-[11px] opacity-80">{count}</span>}
          </button>
        ))}
      </div>

      {/* Feed (announcements + questions) */}
      {section === 'feed' && (
        <div className="space-y-3">
          {isAuthed && <Composer assetId={assetId} kind="question" isHolder={isHolder} onPosted={load} />}
          {stream.length === 0 ? <Empty text="Ще немає оголошень і питань." /> : stream.map((p) => (
            <PostCard key={p.id} post={p} canInteract={isAuthed} onChanged={load} />
          ))}
        </div>
      )}

      {/* Lounge (holder discussions) */}
      {section === 'lounge' && (
        <div className="space-y-3">
          {isHolder ? (
            <>
              <Composer assetId={assetId} kind="discussion" isHolder onPosted={load} />
              {lounge.length === 0 ? <Empty text="Започаткуйте перше обговорення зі співвласниками." /> : lounge.map((p) => (
                <PostCard key={p.id} post={p} canInteract={isHolder} onChanged={load} />
              ))}
            </>
          ) : (
            <div className="rounded-2xl border border-dashed border-border p-10 text-center" data-testid="lounge-locked">
              <Lock className="w-8 h-8 mx-auto text-muted-foreground" />
              <p className="mt-3 font-medium">Ownership Lounge</p>
              <p className="text-sm text-muted-foreground mt-1">Приватний простір співвласників цього об'єкта. Доступ відкривається, щойно ви володієте частками.</p>
            </div>
          )}
        </div>
      )}

      {/* Polls */}
      {section === 'polls' && (
        <div className="space-y-3">
          {polls.length === 0 ? <Empty text="Активних голосувань поки немає." /> : polls.map((p) => (
            <PollCard key={p.id} poll={p} canVote={isHolder} onVoted={load} />
          ))}
          {!isHolder && polls.length > 0 && <p className="text-[11px] text-muted-foreground text-center">Голосувати можуть лише власники часток.</p>}
        </div>
      )}

      {/* Leaderboard */}
      {section === 'leaders' && (
        <div className="rounded-2xl border border-border bg-card p-5">
          <h3 className="font-semibold mb-3 flex items-center gap-2"><Trophy className="w-4 h-4 text-[#C99B3D]" />Найактивніші учасники</h3>
          {leaders.length === 0 ? <Empty text="Поки що тихо. Будьте першим!" /> : (
            <div className="space-y-2">
              {leaders.map((r, i) => (
                <div key={r.user_id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted/40" data-testid={`leader-${i}`}>
                  <span className="w-6 text-center font-bold text-muted-foreground">{i + 1}</span>
                  <span className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-semibold">{initials(r.name)}</span>
                  <span className="font-medium text-sm">{r.name}</span>
                  <RepChip rep={r} />
                  <span className="ml-auto text-xs text-muted-foreground">{r.posts} постів · {r.comments} коментарів · {r.votes} голосів</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const Empty = ({ text }) => (
  <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">{text}</div>
);
