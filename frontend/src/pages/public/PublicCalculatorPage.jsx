import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Slider } from '@/components/ui/slider';
import PageHero from '@/components/public/PageHero';
import Reveal from '@/components/public/Reveal';
import SectionLabel from '@/components/public/SectionLabel';
import { ArrowRight, TrendingUp, Wallet, PiggyBank, Info } from 'lucide-react';

const PRESETS = [
  { key: 'balanced', label: 'Збалансований (нерухомість)', yield: 15 },
  { key: 'commercial', label: 'Комерція', yield: 18 },
  { key: 'growth', label: 'Зростання (будівництво)', yield: 21 },
];

const usd = (n) => '$' + Math.round(n).toLocaleString('en-US');

export default function PublicCalculatorPage() {
  const [amount, setAmount] = useState(10000);
  const [months, setMonths] = useState(24);
  const [yieldPct, setYieldPct] = useState(15);
  const [preset, setPreset] = useState('balanced');

  useEffect(() => { document.title = 'LUMEN · Калькулятор дохідності'; }, []);

  const choosePreset = (p) => { setPreset(p.key); setYieldPct(p.yield); };

  const result = useMemo(() => {
    const annual = amount * (yieldPct / 100);
    const monthly = annual / 12;
    const totalIncome = monthly * months;
    const total = amount + totalIncome;
    return { monthly, annual, totalIncome, total };
  }, [amount, months, yieldPct]);

  return (
    <>
      <PageHero
        breadcrumb={[{ label: 'Головна', to: '/' }, { label: 'Калькулятор' }]}
        title="Калькулятор дохідності"
        lead="Оцініть прогноз виплат на основі суми інвестиції, терміну та очікуваної дохідності активу."
        watermark="YIELD"
      />

      <section className="lpub-section lpub-section--cream">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
            {/* Inputs */}
            <Reveal>
              <div className="rounded-2xl border border-border bg-white p-6 sm:p-8">
                <SectionLabel>Параметри</SectionLabel>

                <div className="mt-7">
                  <div className="flex items-end justify-between">
                    <label className="text-sm font-medium text-token-muted">Сума інвестиції</label>
                    <span className="font-mono text-xl font-bold text-[#2E5D4F]">{usd(amount)}</span>
                  </div>
                  <input
                    type="range" min={1000} max={200000} step={500} value={amount}
                    onChange={(e) => setAmount(Number(e.target.value))}
                    className="lpub-range mt-3 w-full" data-testid="calculator-invest-amount-input"
                  />
                  <div className="mt-1 flex justify-between text-xs text-token-muted"><span>$1,000</span><span>$200,000</span></div>
                </div>

                <div className="mt-7">
                  <div className="flex items-end justify-between">
                    <label className="text-sm font-medium text-token-muted">Термін</label>
                    <span className="font-mono text-xl font-bold text-[#2E5D4F]">{months} міс.</span>
                  </div>
                  <input
                    type="range" min={6} max={60} step={1} value={months}
                    onChange={(e) => setMonths(Number(e.target.value))}
                    className="lpub-range mt-3 w-full" data-testid="calculator-term-input"
                  />
                  <div className="mt-1 flex justify-between text-xs text-token-muted"><span>6 міс.</span><span>60 міс.</span></div>
                </div>

                <div className="mt-7">
                  <label className="text-sm font-medium text-token-muted">Профіль активу (очікувана дохідність)</label>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {PRESETS.map((p) => (
                      <button key={p.key} type="button" onClick={() => choosePreset(p)}
                        className={`h-9 rounded-full px-3.5 text-sm font-medium transition ${preset === p.key ? 'bg-[#2E5D4F] text-white' : 'border border-border bg-white text-token-muted hover:border-[#2E5D4F]'}`}
                        data-testid={`calculator-preset-${p.key}`}>
                        {p.label} · {p.yield}%
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </Reveal>

            {/* Results */}
            <Reveal delay={0.1}>
              <div className="rounded-2xl bg-[#062614] p-6 sm:p-8 text-white" data-testid="calculator-result">
                <SectionLabel tone="light">Прогноз</SectionLabel>
                <div className="mt-7 grid grid-cols-1 gap-5">
                  <ResultRow icon={Wallet} label="Щомісячна виплата" value={usd(result.monthly)} accent />
                  <div className="grid grid-cols-2 gap-5">
                    <ResultRow icon={TrendingUp} label="Річна дохідність" value={usd(result.annual)} sub={`${yieldPct}% річних`} />
                    <ResultRow icon={PiggyBank} label="Дохід за термін" value={usd(result.totalIncome)} sub={`${months} міс.`} />
                  </div>
                  <div className="rounded-xl border border-white/12 bg-white/[0.04] p-5">
                    <p className="text-xs uppercase tracking-[0.16em] text-white/55">Загальний результат (капітал + дохід)</p>
                    <motion.p key={result.total} initial={{ opacity: 0.4, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
                      className="mt-1 font-mono text-3xl font-bold text-[#E5C98A]">{usd(result.total)}</motion.p>
                  </div>
                </div>
                <Link to="/assets" className="lpub-btn-gold mt-7 w-full justify-center">Обрати актив <ArrowRight className="h-4 w-4" /></Link>
                <p className="mt-4 flex items-start gap-2 text-xs leading-relaxed text-white/45">
                  <Info className="mt-0.5 h-3.5 w-3.5 flex-none" />
                  Орієнтовний розрахунок. Фактична дохідність залежить від умов конкретного активу та ринкових факторів і не є гарантією доходу.
                </p>
              </div>
            </Reveal>
          </div>
        </div>
      </section>
    </>
  );
}

function ResultRow({ icon: Icon, label, value, sub, accent }) {
  return (
    <div className={`rounded-xl border p-5 ${accent ? 'border-[#C9A961]/30 bg-[#C9A961]/[0.06]' : 'border-white/12 bg-white/[0.04]'}`}>
      <div className="flex items-center gap-2 text-white/55"><Icon className="h-4 w-4" /><span className="text-xs uppercase tracking-[0.14em]">{label}</span></div>
      <p className={`mt-1.5 font-mono text-2xl font-bold ${accent ? 'text-[#E5C98A]' : 'text-white'}`}>{value}</p>
      {sub && <p className="text-xs text-white/45">{sub}</p>}
    </div>
  );
}
