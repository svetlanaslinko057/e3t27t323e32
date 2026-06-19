import { Lock, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

/** Shown when a non-qualified investor hits a gated institutional surface (API 403). */
export default function InstitutionalGate({ message }) {
  return (
    <div className="max-w-xl mx-auto p-6" data-testid="institutional-gate">
      <div className="rounded-2xl border border-border bg-card p-8 text-center">
        <div className="w-12 h-12 rounded-full bg-[#2E5D4F]/10 flex items-center justify-center mx-auto mb-4"><Lock className="w-5 h-5 text-[#2E5D4F]" /></div>
        <h2 className="text-lg font-bold">Інституційний кабінет</h2>
        <p className="text-sm text-muted-foreground mt-2">{message || 'Доступ до фондів, синдикатів та інституційної звітності відкривається для кваліфікованих інвесторів (Strategic / Institutional).'}</p>
        <Link to="/investor/dashboard" className="inline-flex items-center gap-1.5 mt-5 h-10 px-4 rounded-lg text-sm font-medium text-white" style={{ background: '#2E5D4F' }}>
          До кабінету інвестора <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}
