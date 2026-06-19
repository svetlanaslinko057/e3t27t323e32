import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import {
  X, Loader2, StickyNote, CheckSquare, CalendarDays, Activity as ActIcon,
  Phone, Send, Repeat, Plus, Check, Clock, ShieldAlert,
} from 'lucide-react';

const STAGE = {
  lead: ['Лід', 'Lead'], qualified: ['Кваліфіковано', 'Qualified'], meeting: ['Зустріч', 'Meeting'],
  kyc: ['KYC', 'KYC'], accredited: ['Акредитовано', 'Accredited'], funding_pending: ['Очікує фандинг', 'Funding pending'],
  funded: ['Профінансовано', 'Funded'], active: ['Активний', 'Active'],
};
const EARLY = ['lead', 'qualified', 'meeting'];
const HEALTH_BADGE = { green: 'bg-emerald-100 text-emerald-700', yellow: 'bg-amber-100 text-amber-700', red: 'bg-rose-100 text-rose-700' };
const SLA_BADGE = { responded: 'bg-emerald-100 text-emerald-700', pending: 'bg-sky-100 text-sky-700', breached: 'bg-rose-100 text-rose-700' };
const PRIO_BADGE = { A: 'bg-rose-100 text-rose-700', B: 'bg-amber-100 text-amber-700', C: 'bg-sky-100 text-sky-700', D: 'bg-slate-100 text-slate-600' };
const COMM_TYPES = ['call', 'email', 'telegram', 'whatsapp', 'sms', 'document', 'other'];

/**
 * LeadDrawer — full working lead workspace (shared by Manager + Admin).
 * Tabs: Overview · Notes · Tasks · Meetings · Timeline.
 * Actions: change stage, reassign (transfer), log communication, convert.
 * All calls go to /api/admin/ir/* which the backend scopes per staff user.
 */
export default function LeadDrawer({ leadId, managers = [], onClose, onChanged }) {
  const { bi, lang } = useLang();
  const L = (a) => (lang === 'en' ? 1 : 0) ? a[1] : a[0];
  const sl = (s) => (STAGE[s] ? STAGE[s][lang === 'en' ? 1 : 0] : s);

  const [tab, setTab] = useState('overview');
  const [lead, setLead] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const [notes, setNotes] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [timeline, setTimeline] = useState([]);

  const [noteBody, setNoteBody] = useState('');
  const [taskForm, setTaskForm] = useState({ title: '', due_date: '', priority: 'normal', task_type: '' });
  const [meetForm, setMeetForm] = useState({ title: '', scheduled_at: '', type: 'call', duration_min: 30 });
  const [commForm, setCommForm] = useState({ interaction_type: 'call', direction: 'outbound', detail: '' });
  const [reassignTo, setReassignTo] = useState('');
  const [reassignReason, setReassignReason] = useState('');

  const loadLead = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const r = await lumen.get(`/admin/ir/leads/${leadId}`);
      setLead(r.data);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, [leadId]);

  const loadTab = useCallback(async (which) => {
    try {
      if (which === 'notes') setNotes((await lumen.get(`/admin/ir/leads/${leadId}/notes`)).data?.notes || []);
      else if (which === 'tasks') setTasks((await lumen.get(`/admin/ir/leads/${leadId}/tasks`)).data?.tasks || []);
      else if (which === 'meetings') setMeetings((await lumen.get(`/admin/ir/leads/${leadId}/meetings`)).data?.meetings || []);
      else if (which === 'timeline') setTimeline((await lumen.get(`/admin/ir/leads/${leadId}/timeline`)).data?.timeline || []);
    } catch (e) { setErr(lumenError(e)); }
  }, [leadId]);

  useEffect(() => { loadLead(); }, [loadLead]);
  useEffect(() => { if (tab !== 'overview') loadTab(tab); }, [tab, loadTab]);

  const refreshAll = async () => { await loadLead(); onChanged && onChanged(); };

  const doStage = async (stage) => {
    setBusy(true);
    try { await lumen.post(`/admin/ir/leads/${leadId}/stage`, { stage }); await refreshAll(); }
    catch (e) { setErr(lumenError(e)); } finally { setBusy(false); }
  };
  const doReassign = async () => {
    if (!reassignTo) return;
    setBusy(true);
    try {
      await lumen.post(`/admin/ir/leads/${leadId}/reassign`, { to_owner_id: reassignTo, reason: reassignReason || 'manual transfer' });
      setReassignTo(''); setReassignReason(''); await refreshAll();
    } catch (e) { setErr(lumenError(e)); } finally { setBusy(false); }
  };
  const addNote = async () => {
    if (!noteBody.trim()) return;
    setBusy(true);
    try { await lumen.post(`/admin/ir/leads/${leadId}/notes`, { body: noteBody }); setNoteBody(''); await loadTab('notes'); await loadLead(); }
    catch (e) { setErr(lumenError(e)); } finally { setBusy(false); }
  };
  const addTask = async () => {
    if (!taskForm.title.trim()) return;
    setBusy(true);
    try { await lumen.post(`/admin/ir/leads/${leadId}/tasks`, taskForm); setTaskForm({ title: '', due_date: '', priority: 'normal', task_type: '' }); await loadTab('tasks'); }
    catch (e) { setErr(lumenError(e)); } finally { setBusy(false); }
  };
  const completeTask = async (id) => {
    try { await lumen.patch(`/admin/ir/tasks/${id}`, { status: 'done' }); await loadTab('tasks'); await loadLead(); }
    catch (e) { setErr(lumenError(e)); }
  };
  const addMeeting = async () => {
    if (!meetForm.title.trim() || !meetForm.scheduled_at) return;
    setBusy(true);
    try {
      await lumen.post(`/admin/ir/leads/${leadId}/meetings`, { ...meetForm, scheduled_at: new Date(meetForm.scheduled_at).toISOString() });
      setMeetForm({ title: '', scheduled_at: '', type: 'call', duration_min: 30 }); await loadTab('meetings');
    } catch (e) { setErr(lumenError(e)); } finally { setBusy(false); }
  };
  const completeMeeting = async (id) => {
    try { await lumen.patch(`/admin/ir/meetings/${id}`, { status: 'completed' }); await loadTab('meetings'); await loadLead(); }
    catch (e) { setErr(lumenError(e)); }
  };
  const logComm = async () => {
    setBusy(true);
    try { await lumen.post(`/admin/ir/leads/${leadId}/communications`, commForm); setCommForm({ interaction_type: 'call', direction: 'outbound', detail: '' }); await refreshAll(); if (tab === 'timeline') loadTab('timeline'); }
    catch (e) { setErr(lumenError(e)); } finally { setBusy(false); }
  };

  const TABS = [
    ['overview', bi('Огляд', 'Overview'), ActIcon],
    ['notes', bi('Нотатки', 'Notes'), StickyNote],
    ['tasks', bi('Задачі', 'Tasks'), CheckSquare],
    ['meetings', bi('Зустрічі', 'Meetings'), CalendarDays],
    ['timeline', bi('Таймлайн', 'Timeline'), ActIcon],
  ];

  const sla = lead?.sla || {};
  const prio = lead?.priority || {};
  const health = lead?.health || {};

  return (
    <div className="fixed inset-0 z-[9998] flex justify-end" data-testid="lead-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-card h-full shadow-2xl flex flex-col border-l border-border">
        {/* header */}
        <div className="px-5 py-4 border-b border-border flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-bold truncate text-token-primary">{lead?.full_name || lead?.email || bi('Лід', 'Lead')}</h2>
            <p className="text-xs text-token-muted truncate">{lead?.email} {lead?.phone ? `· ${lead.phone}` : ''}</p>
            <div className="flex flex-wrap items-center gap-1.5 mt-2">
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-token-primary">{sl(lead?.effective_stage)}</span>
              {health.color && <span className={`text-[11px] px-2 py-0.5 rounded-full ${HEALTH_BADGE[health.color]}`}>{health.color}</span>}
              {sla.status && <span className={`text-[11px] px-2 py-0.5 rounded-full ${SLA_BADGE[sla.status] || 'bg-slate-100'}`}>SLA: {sla.status}</span>}
              {prio.bucket && <span className={`text-[11px] px-2 py-0.5 rounded-full ${PRIO_BADGE[prio.bucket]}`}>{prio.bucket} · {prio.label}</span>}
            </div>
          </div>
          <button onClick={onClose} data-testid="drawer-close" className="p-1.5 rounded-lg text-token-muted hover:text-token-primary"><X className="w-5 h-5" /></button>
        </div>
        {/* tabs */}
        <div className="flex border-b border-border overflow-x-auto">
          {TABS.map(([k, label, Icon]) => (
            <button key={k} onClick={() => setTab(k)} data-testid={`drawer-tab-${k}`}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition ${tab === k ? 'border-[var(--token-primary)] text-token-primary' : 'border-transparent text-token-muted hover:text-token-primary'}`}>
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </div>

        {err && <p className="px-5 py-2 text-sm text-rose-600" data-testid="drawer-error">{err}</p>}

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {loading ? (
            <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>
          ) : tab === 'overview' ? (
            <>
              {/* SLA + facts */}
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Info label={bi('Джерело', 'Source')} value={lead?.source} />
                <Info label={bi('Інтерес', 'Interest')} value={lead?.interest || '—'} />
                <Info label={bi('Власник', 'Owner')} value={lead?.owner_name || bi('Не призначено', 'Unassigned')} />
                <Info label={bi('Час 1-ї відповіді', 'First response')} value={sla.first_response_min != null ? `${sla.first_response_min} ${bi('хв', 'min')}` : '—'} />
              </div>
              {(health.reasons || []).length > 0 && (
                <div className="rounded-xl border border-border p-3 text-sm">
                  <div className="text-xs uppercase tracking-wider text-token-muted mb-1">Health</div>
                  <ul className="list-disc pl-4 text-token-primary space-y-0.5">{health.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </div>
              )}
              {/* change stage */}
              <div className="rounded-xl border border-border p-3">
                <div className="text-xs uppercase tracking-wider text-token-muted mb-2">{bi('Стадія (рання — вручну)', 'Stage (early — manual)')}</div>
                <div className="flex flex-wrap gap-2">
                  {EARLY.map((s) => (
                    <button key={s} disabled={busy} onClick={() => doStage(s)} data-testid={`stage-${s}`}
                      className={`text-xs px-2.5 py-1 rounded-lg border ${lead?.manual_stage === s ? 'border-[var(--token-primary)] text-token-primary font-semibold' : 'border-border text-token-muted hover:text-token-primary'}`}>
                      {sl(s)}
                    </button>
                  ))}
                </div>
              </div>
              {/* reassign / transfer */}
              <div className="rounded-xl border border-border p-3 space-y-2">
                <div className="text-xs uppercase tracking-wider text-token-muted flex items-center gap-1.5"><Repeat className="w-3.5 h-3.5" /> {bi('Передати власника', 'Transfer owner')}</div>
                <select value={reassignTo} onChange={(e) => setReassignTo(e.target.value)} data-testid="reassign-select" className="w-full h-9 px-2 rounded-lg border border-border bg-background text-sm">
                  <option value="">{bi('Обрати менеджера…', 'Select manager…')}</option>
                  {managers.map((m) => <option key={m.user_id} value={m.user_id}>{m.name} ({m.email})</option>)}
                </select>
                <input value={reassignReason} onChange={(e) => setReassignReason(e.target.value)} placeholder={bi('Причина (необов’язково)', 'Reason (optional)')} className="w-full h-9 px-2 rounded-lg border border-border bg-background text-sm" data-testid="reassign-reason" />
                <button disabled={busy || !reassignTo} onClick={doReassign} data-testid="reassign-submit" className="w-full h-9 rounded-lg text-sm font-medium text-white disabled:opacity-50" style={{ background: 'var(--token-primary)' }}>{bi('Передати', 'Transfer')}</button>
              </div>
              {/* log communication */}
              <div className="rounded-xl border border-border p-3 space-y-2">
                <div className="text-xs uppercase tracking-wider text-token-muted flex items-center gap-1.5"><Phone className="w-3.5 h-3.5" /> {bi('Зафіксувати комунікацію', 'Log communication')}</div>
                <div className="flex gap-2">
                  <select value={commForm.interaction_type} onChange={(e) => setCommForm({ ...commForm, interaction_type: e.target.value })} data-testid="comm-type" className="flex-1 h-9 px-2 rounded-lg border border-border bg-background text-sm">
                    {COMM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <select value={commForm.direction} onChange={(e) => setCommForm({ ...commForm, direction: e.target.value })} className="h-9 px-2 rounded-lg border border-border bg-background text-sm">
                    <option value="outbound">{bi('Вихідний', 'Outbound')}</option>
                    <option value="inbound">{bi('Вхідний', 'Inbound')}</option>
                  </select>
                </div>
                <input value={commForm.detail} onChange={(e) => setCommForm({ ...commForm, detail: e.target.value })} placeholder={bi('Деталі…', 'Details…')} className="w-full h-9 px-2 rounded-lg border border-border bg-background text-sm" data-testid="comm-detail" />
                <button disabled={busy} onClick={logComm} data-testid="comm-submit" className="w-full h-9 rounded-lg text-sm font-medium border border-border hover:bg-muted inline-flex items-center justify-center gap-1.5"><Send className="w-3.5 h-3.5" /> {bi('Зафіксувати', 'Log')}</button>
              </div>
            </>
          ) : tab === 'notes' ? (
            <>
              <div className="flex gap-2">
                <input value={noteBody} onChange={(e) => setNoteBody(e.target.value)} placeholder={bi('Нова нотатка…', 'New note…')} data-testid="note-input" className="flex-1 h-10 px-3 rounded-lg border border-border bg-background text-sm" />
                <button disabled={busy} onClick={addNote} data-testid="note-add" className="h-10 px-3 rounded-lg text-white text-sm" style={{ background: 'var(--token-primary)' }}><Plus className="w-4 h-4" /></button>
              </div>
              {notes.length === 0 ? <Empty bi={bi} /> : notes.map((n) => (
                <div key={n.id} className="rounded-xl border border-border p-3" data-testid="note-row">
                  <p className="text-sm text-token-primary">{n.body}</p>
                  <p className="text-[11px] text-token-muted mt-1">{n.author_name} · {formatDateUk(n.created_at)}</p>
                </div>
              ))}
            </>
          ) : tab === 'tasks' ? (
            <>
              <div className="rounded-xl border border-border p-3 space-y-2">
                <input value={taskForm.title} onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })} placeholder={bi('Назва задачі', 'Task title')} data-testid="task-title" className="w-full h-9 px-2 rounded-lg border border-border bg-background text-sm" />
                <div className="flex gap-2">
                  <input type="date" value={taskForm.due_date} onChange={(e) => setTaskForm({ ...taskForm, due_date: e.target.value })} data-testid="task-due" className="flex-1 h-9 px-2 rounded-lg border border-border bg-background text-sm" />
                  <select value={taskForm.priority} onChange={(e) => setTaskForm({ ...taskForm, priority: e.target.value })} className="h-9 px-2 rounded-lg border border-border bg-background text-sm">
                    <option value="low">low</option><option value="normal">normal</option><option value="high">high</option>
                  </select>
                </div>
                <button disabled={busy} onClick={addTask} data-testid="task-add" className="w-full h-9 rounded-lg text-white text-sm" style={{ background: 'var(--token-primary)' }}>{bi('Додати задачу', 'Add task')}</button>
              </div>
              {tasks.length === 0 ? <Empty bi={bi} /> : tasks.map((t) => (
                <div key={t.id} className="rounded-xl border border-border p-3 flex items-center justify-between gap-3" data-testid="task-row">
                  <div className="min-w-0">
                    <p className={`text-sm ${t.status === 'done' ? 'line-through text-token-muted' : 'text-token-primary'}`}>{t.title}</p>
                    <p className="text-[11px] text-token-muted">{t.priority} {t.due_date ? `· ${formatDateUk(t.due_date)}` : ''}</p>
                  </div>
                  {t.status !== 'done' && <button onClick={() => completeTask(t.id)} data-testid="task-done" className="p-1.5 rounded-lg border border-border text-emerald-600 hover:bg-muted"><Check className="w-4 h-4" /></button>}
                </div>
              ))}
            </>
          ) : tab === 'meetings' ? (
            <>
              <div className="rounded-xl border border-border p-3 space-y-2">
                <input value={meetForm.title} onChange={(e) => setMeetForm({ ...meetForm, title: e.target.value })} placeholder={bi('Назва зустрічі', 'Meeting title')} data-testid="meet-title" className="w-full h-9 px-2 rounded-lg border border-border bg-background text-sm" />
                <div className="flex gap-2">
                  <input type="datetime-local" value={meetForm.scheduled_at} onChange={(e) => setMeetForm({ ...meetForm, scheduled_at: e.target.value })} data-testid="meet-when" className="flex-1 h-9 px-2 rounded-lg border border-border bg-background text-sm" />
                  <select value={meetForm.type} onChange={(e) => setMeetForm({ ...meetForm, type: e.target.value })} className="h-9 px-2 rounded-lg border border-border bg-background text-sm">
                    <option value="call">call</option><option value="video">video</option><option value="in_person">in person</option>
                  </select>
                </div>
                <button disabled={busy} onClick={addMeeting} data-testid="meet-add" className="w-full h-9 rounded-lg text-white text-sm" style={{ background: 'var(--token-primary)' }}>{bi('Запланувати', 'Schedule')}</button>
              </div>
              {meetings.length === 0 ? <Empty bi={bi} /> : meetings.map((m) => (
                <div key={m.id} className="rounded-xl border border-border p-3 flex items-center justify-between gap-3" data-testid="meet-row">
                  <div className="min-w-0">
                    <p className="text-sm text-token-primary">{m.title}</p>
                    <p className="text-[11px] text-token-muted">{m.type} · {formatDateUk(m.scheduled_at)} · {m.status}</p>
                  </div>
                  {m.status === 'scheduled' && <button onClick={() => completeMeeting(m.id)} data-testid="meet-done" className="p-1.5 rounded-lg border border-border text-emerald-600 hover:bg-muted"><Check className="w-4 h-4" /></button>}
                </div>
              ))}
            </>
          ) : (
            <>
              {timeline.length === 0 ? <Empty bi={bi} /> : (
                <ol className="relative border-l border-border pl-4 space-y-4">
                  {timeline.map((e, i) => (
                    <li key={i} data-testid="timeline-item">
                      <span className="absolute -left-1.5 w-3 h-3 rounded-full" style={{ background: 'var(--token-primary)' }} />
                      <p className="text-sm font-medium text-token-primary">{e.title}</p>
                      {e.detail && <p className="text-xs text-token-muted">{e.detail}</p>}
                      <p className="text-[11px] text-token-muted">{formatDateUk(e.at)} {e.actor ? `· ${e.actor}` : ''}</p>
                    </li>
                  ))}
                </ol>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Info({ label, value }) {
  return (
    <div className="rounded-xl border border-border p-3">
      <div className="text-[11px] uppercase tracking-wider text-token-muted">{label}</div>
      <div className="text-sm font-medium text-token-primary truncate mt-0.5">{value}</div>
    </div>
  );
}
function Empty({ bi }) {
  return <p className="text-sm text-token-muted text-center py-8">{bi('Поки порожньо', 'Nothing yet')}</p>;
}
