import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Building2, Coins, TrendingUp, ShieldCheck, ArrowRight } from 'lucide-react';
import PageHero from '@/components/public/PageHero';
import Reveal from '@/components/public/Reveal';
import SectionLabel from '@/components/public/SectionLabel';
import AssetYieldCalculator from '@/components/public/AssetYieldCalculator';

const MODEL_STEPS = [
  {
    icon: Building2,
    title: 'Обираєте реальний об\'єкт',
    desc: 'Кожен актив має власну економіку: обсяг пулу, цільову IRR, горизонт та мінімальну частку. Ви інвестуєте не «в платформу», а у конкретний об\'єкт.',
  },
  {
    icon: Coins,
    title: 'Орендний грошовий потік',
    desc: 'Для нерухомості та комерції частина доходу — це регулярні орендні виплати, пропорційні вашій частці у пулі.',
  },
  {
    icon: TrendingUp,
    title: 'Переоцінка при виході',
    desc: 'Решта доходу фіксується при завершенні раунду — продажу активу або викупі оператором. Для будівництва/землі це основна складова.',
  },
  {
    icon: ShieldCheck,
    title: 'Чесний розрахунок «нетто»',
    desc: 'Ми показуємо валовий і чистий прибуток із врахуванням податку (19.5%) та три сценарії — консервативний, базовий, оптимістичний.',
  },
];

export default function PublicCalculatorPage() {
  useEffect(() => { document.title = 'LUMEN · Калькулятор дохідності'; }, []);

  return (
    <>
      <PageHero
        breadcrumb={[{ label: 'Головна', to: '/' }, { label: 'Калькулятор' }]}
        title="Прорахуйте свою позицію в об'єкті"
        lead="Ви купуєте частку у пулі, що фінансує реальний об'єкт. Оберіть актив, вкажіть суму — і побачите чесну розбивку: частку в пулі, грошовий потік, переоцінку, чистий прибуток, IRR та сценарії."
        watermark="YIELD"
      />

      {/* Calculator */}
      <section className="lpub-section lpub-section--cream">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <Reveal>
            <SectionLabel>модель частки в активі</SectionLabel>
            <h2 className="lpub-h2 mt-3 max-w-3xl">Дохід — це ваша частка від реальної економіки активу</h2>
          </Reveal>
          <div className="mt-10">
            <AssetYieldCalculator />
          </div>
        </div>
      </section>

      {/* How the model works — blocks */}
      <section className="lpub-section">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <Reveal>
            <SectionLabel>як рахується дохід</SectionLabel>
            <h2 className="lpub-h2 mt-3 max-w-3xl">Звідки беруться цифри у прогнозі</h2>
          </Reveal>

          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {MODEL_STEPS.map((s, i) => (
              <Reveal key={s.title} delay={i * 0.06}>
                <div className="h-full rounded-2xl border border-border bg-white p-6">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#2E5D4F]/8 text-[#2E5D4F]">
                    <s.icon className="h-5 w-5" />
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-foreground">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-token-muted">{s.desc}</p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal delay={0.1}>
            <div className="mt-10 flex flex-col items-start gap-4 rounded-2xl border border-border bg-[#F7F5EF] p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
              <div>
                <p className="text-base font-semibold text-foreground">Готові підібрати об'єкт під вашу мету?</p>
                <p className="mt-1 text-sm text-token-muted">Перегляньте відкриті раунди з повною економікою кожного активу.</p>
              </div>
              <Link to="/assets" className="lpub-btn-gold flex-none justify-center">
                Переглянути активи <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
