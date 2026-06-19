import { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Printer, FileText, ShieldCheck, Scale, UserCheck, AlertTriangle, Repeat, Check } from 'lucide-react';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import MarkdownLite from '@/components/MarkdownLite';
import { lumen, formatDateUk } from '@/lib/lumenApi';

const ICONS = {
  offer: FileText, privacy: ShieldCheck, aml: Scale,
  kyc: UserCheck, risk: AlertTriangle, secondary: Repeat,
};

export default function LegalDocPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState(null);
  const [pkg, setPkg] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setNotFound(false);
    Promise.all([
      lumen.get(`/public/legal-document/${slug}`).then((r) => r.data).catch(() => null),
      lumen.get('/public/legal-package').then((r) => r.data?.items || []).catch(() => []),
    ]).then(([d, items]) => {
      if (!active) return;
      if (!d) { setNotFound(true); } else { setDoc(d); document.title = `Lumen · ${d.title}`; }
      setPkg(items);
      setLoading(false);
    });
    return () => { active = false; };
  }, [slug]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="w-9 h-9 border-2 border-border border-t-[#2E5D4F] rounded-full animate-spin" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center gap-4 p-6">
        <AlertTriangle className="w-10 h-10 text-muted-foreground" />
        <p className="text-lg font-semibold">Документ не знайдено</p>
        <Link to="/legal" className="text-[#2E5D4F] hover:underline text-sm">Повернутись до правової інформації</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="legal-doc-page">
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-background/80 border-b border-border print:hidden">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="legal-doc-home">
            <ArrowLeft className="w-4 h-4 text-muted-foreground" />
            <Logo height={30} />
          </Link>
          <div className="flex items-center gap-2">
            <button
              onClick={() => window.print()}
              className="hidden sm:inline-flex items-center gap-2 px-3 h-9 rounded-full border border-border text-sm text-muted-foreground hover:text-foreground transition"
              data-testid="legal-print"
            >
              <Printer className="w-4 h-4" /> Друк
            </button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-10 md:py-14 grid lg:grid-cols-12 gap-10">
        {/* TOC / package nav */}
        <aside className="lg:col-span-4 xl:col-span-3 print:hidden">
          <div className="lg:sticky lg:top-24">
            <Link to="/legal" className="text-xs uppercase tracking-widest text-[#2E5D4F] font-semibold hover:underline">
              ← Правова інформація
            </Link>
            <nav className="mt-4 space-y-1" data-testid="legal-toc">
              {pkg.map((it) => {
                const Icon = ICONS[it.kind] || FileText;
                const active = it.slug === slug || it.kind === doc?.kind;
                return (
                  <button
                    key={it.kind}
                    onClick={() => navigate(`/legal/${it.slug}`)}
                    data-testid={`legal-toc-${it.slug}`}
                    className={`w-full text-left flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm transition ${
                      active
                        ? 'bg-[#2E5D4F]/10 text-[#2E5D4F] font-semibold'
                        : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span className="flex-1">{it.title}</span>
                    {active && <Check className="w-4 h-4" />}
                  </button>
                );
              })}
            </nav>
          </div>
        </aside>

        {/* Document */}
        <article className="lg:col-span-8 xl:col-span-9 min-w-0">
          <div className="rounded-2xl border border-border bg-card p-6 md:p-10">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
              <span>Оновлено {formatDateUk(doc?.updated_at)}</span>
            </div>
            <div className="text-foreground" data-testid="legal-doc-body">
              <MarkdownLite text={doc?.body} />
            </div>
          </div>
          <p className="mt-6 text-xs text-muted-foreground leading-relaxed">
            Цей документ є частиною правового пакета Lumen. Із повним переліком документів можна
            ознайомитися на сторінці <Link to="/legal" className="text-[#2E5D4F] hover:underline">Правова інформація</Link>.
          </p>
        </article>
      </div>
    </div>
  );
}
