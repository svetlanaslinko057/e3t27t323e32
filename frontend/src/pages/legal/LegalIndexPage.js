import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, FileText, ShieldCheck, Scale, UserCheck, AlertTriangle, Repeat, ArrowRight } from 'lucide-react';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import { lumen, formatDateUk } from '@/lib/lumenApi';

const ICONS = {
  offer: FileText,
  privacy: ShieldCheck,
  aml: Scale,
  kyc: UserCheck,
  risk: AlertTriangle,
  secondary: Repeat,
};

export default function LegalIndexPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.title = 'Lumen · Правова інформація';
    lumen.get('/public/legal-package')
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="legal-index-page">
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-background/80 border-b border-border">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="legal-home">
            <ArrowLeft className="w-4 h-4 text-muted-foreground" />
            <Logo height={30} />
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-12 md:py-16">
        <p className="text-xs uppercase tracking-widest text-[#2E5D4F] font-semibold">Правова інформація</p>
        <h1 className="mt-2 text-3xl md:text-4xl font-bold tracking-tight">Документи та політики Lumen</h1>
        <p className="mt-3 text-muted-foreground max-w-2xl leading-relaxed">
          Повний правовий пакет платформи. Ознайомтеся з умовами участі, обробкою даних,
          фінансовим моніторингом та розкриттям ризиків перед інвестуванням.
        </p>

        {loading ? (
          <div className="mt-10 grid sm:grid-cols-2 gap-4">
            {[...Array(6)].map((_, i) => <div key={i} className="h-32 rounded-2xl bg-card border border-border animate-pulse" />)}
          </div>
        ) : (
          <div className="mt-10 grid sm:grid-cols-2 gap-4">
            {items.map((it) => {
              const Icon = ICONS[it.kind] || FileText;
              return (
                <Link
                  key={it.kind}
                  to={`/legal/${it.slug}`}
                  data-testid={`legal-card-${it.slug}`}
                  className="group rounded-2xl border border-border bg-card p-6 hover:border-[#2E5D4F]/40 hover:shadow-lg transition flex flex-col"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center group-hover:scale-105 transition">
                      <Icon className="w-5 h-5" />
                    </div>
                    <h2 className="font-semibold text-lg leading-snug">{it.title}</h2>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground leading-relaxed flex-1">{it.summary}</p>
                  <div className="mt-4 flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Оновлено {formatDateUk(it.updated_at)}</span>
                    <span className="inline-flex items-center gap-1 text-[#2E5D4F] font-medium">
                      Читати <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition" />
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
