import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatDateUk, lumenError } from '@/lib/lumenApi';
import {
  MessageCircleQuestion, Loader2, CheckCircle2, AlertCircle, Send,
} from 'lucide-react';

const FILTERS = [
  { value: 'pending',  label: 'Очікують' },
  { value: '',         label: 'Всі' },
  { value: 'answered', label: 'З відповіддю' },
  { value: 'hidden',   label: 'Приховані' },
];

export default function AdminQuestions() {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [filter, setFilter] = useState('pending');
  const [loading, setLoading] = useState(true);
  const [answers, setAnswers] = useState({});
  const [actingId, setActingId] = useState('');
  const [flash, setFlash] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async (f = filter) => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/questions' + (f ? `?status=${f}` : ''));
      setItems(r.data?.items || []);
      setCounts(r.data?.counts || {});
    } catch (_e) {
      setError('Не вдалось завантажити питання');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const answer = async (id) => {
    setActingId(id);
    setError('');
    try {
      await lumen.post(`/admin/questions/${id}/answer`, { answer: answers[id] || '' });
      setFlash('Відповідь опубліковано — інвестора повідомлено');
      setTimeout(() => setFlash(''), 4000);
      setAnswers((p) => ({ ...p, [id]: '' }));
      await load();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось опублікувати відповідь'));
    } finally {
      setActingId('');
    }
  };

  const toggleHide = async (q) => {
    try {
      await lumen.post(`/admin/questions/${q.id}/${q.status === 'hidden' ? 'restore' : 'hide'}`);
      await load();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось змінити видимість'));
    }
  };

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto" data-testid="admin-questions">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-token-muted">Контент і довіра</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Питання інвесторів (Q&A)</h1>
        <p className="mt-1 text-token-muted text-sm">Відповіді публічні — їх бачать усі відвідувачі сторінки активу.</p>
      </header>

      {flash && (
        <div className="mb-4 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2" data-testid="questions-flash">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-center gap-2" data-testid="questions-error">
          <AlertCircle className="w-4 h-4" /> {String(error)}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-6" data-testid="questions-filters">
        {FILTERS.map((f) => {
          const count = f.value === ''
            ? Object.values(counts).reduce((a, b) => a + (b || 0), 0)
            : (counts[f.value] || 0);
          return (
            <button
              key={f.value || 'all'}
              onClick={() => setFilter(f.value)}
              className={`px-4 h-9 rounded-full text-sm font-medium border transition ${filter === f.value ? 'bg-foreground text-background border-foreground' : 'border-border hover:border-[#2E5D4F]'}`}
              data-testid={`questions-filter-${f.value || 'all'}`}
            >
              {f.label}{count > 0 && <span className="ml-1.5 opacity-70">{count}</span>}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="p-10 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="questions-empty">
          <MessageCircleQuestion className="w-6 h-6 mx-auto mb-2 opacity-40" />
          Питань немає
        </div>
      ) : (
        <div className="space-y-4" data-testid="questions-list">
          {items.map((q) => (
            <div key={q.id} className="rounded-2xl border border-border bg-card p-5" data-testid={`question-item-${q.id}`}>
              <div className="flex items-center gap-2 flex-wrap">
                <p className="font-medium text-sm">{q.investor_name}</p>
                <Link to={`/admin/assets/${q.asset_id}/content`} className="text-xs text-[#2E5D4F] hover:underline">{q.asset_title}</Link>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${q.status === 'pending' ? 'bg-amber-100 text-amber-800' : q.status === 'answered' ? 'bg-emerald-100 text-emerald-800' : 'bg-muted text-muted-foreground'}`}>
                  {q.status === 'pending' ? 'очікує відповіді' : q.status === 'answered' ? 'відповідь дано' : 'приховано'}
                </span>
                <span className="text-xs text-muted-foreground ml-auto">{formatDateUk(q.created_at)}</span>
                <button onClick={() => toggleHide(q)} className="text-xs text-muted-foreground hover:text-foreground" data-testid={`question-hide-${q.id}`}>
                  {q.status === 'hidden' ? 'Відновити' : 'Приховати'}
                </button>
              </div>
              <p className="mt-2 text-sm">{q.question}</p>
              {q.answer && (
                <p className="mt-2 text-sm text-muted-foreground border-l-2 border-[#2E5D4F]/40 pl-3">{q.answer}</p>
              )}
              {q.status === 'pending' && (
                <div className="mt-3 flex gap-2">
                  <input
                    value={answers[q.id] || ''}
                    onChange={(e) => setAnswers((p) => ({ ...p, [q.id]: e.target.value }))}
                    placeholder="Ваша публічна відповідь…"
                    className="flex-1 h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm"
                    data-testid={`question-answer-input-${q.id}`}
                  />
                  <button
                    onClick={() => answer(q.id)}
                    disabled={actingId === q.id || !(answers[q.id] || '').trim()}
                    className="shrink-0 inline-flex items-center gap-1.5 px-4 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-40"
                    data-testid={`question-answer-send-${q.id}`}
                  >
                    {actingId === q.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    Відповісти
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
