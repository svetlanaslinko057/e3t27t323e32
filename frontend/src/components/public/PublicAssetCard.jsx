import { Link } from 'react-router-dom';
import { MapPin, TrendingUp, ArrowUpRight } from 'lucide-react';
import { usdFromUah, formatUSD } from '@/lib/lumenApi';

const CATEGORY_LABELS = {
  real_estate: 'нерухомість',
  construction: 'будівництво',
  commercial: 'комерція',
  land: 'земля',
  business: 'бізнес',
};

/**
 * Public asset card — cover, title, location, yield, min ticket, round progress.
 * min_ticket / round amounts are stored in UAH; convert to USD for display.
 */
export const PublicAssetCard = ({ asset }) => {
  const a = asset || {};
  const cat = a.category_label || CATEGORY_LABELS[a.category] || a.category || 'актив';
  const minUsd = a.min_ticket ? formatUSD(usdFromUah(a.min_ticket)) : null;
  const target = Number(a.round_target || 0);
  const raised = Number(a.raised ?? a.raised_amount ?? 0);
  const progress = a.progress_percent != null
    ? Math.round(a.progress_percent)
    : (target > 0 ? Math.min(100, Math.round((raised / target) * 100)) : 0);

  return (
    <Link to={`/objects/${a.id}`} className="lpub-asset group" data-testid="asset-card">
      <div className="lpub-asset__media">
        {a.cover_url
          ? <img src={a.cover_url} alt={a.title} loading="lazy" draggable={false} />
          : <div className="lpub-asset__media-fallback" />}
        <span className="lpub-asset__cat">{cat}</span>
        {a.target_yield != null && (
          <span className="lpub-asset__yield"><TrendingUp className="h-3.5 w-3.5" /> {a.target_yield}% <i>річних</i></span>
        )}
      </div>
      <div className="lpub-asset__body">
        <h3 className="lpub-asset__title">{a.title}</h3>
        {a.location && (
          <p className="lpub-asset__loc"><MapPin className="h-3.5 w-3.5" /> {a.location}</p>
        )}
        <div className="lpub-asset__progress" data-testid="asset-card-progress">
          <div className="lpub-asset__progress-bar"><span style={{ width: `${progress}%` }} /></div>
          <div className="lpub-asset__progress-meta">
            <span>Зібрано {progress}%</span>
            {minUsd && <span>від {minUsd}</span>}
          </div>
        </div>
        <span className="lpub-asset__cta">Деталі активу <ArrowUpRight className="h-4 w-4" /></span>
      </div>
    </Link>
  );
};

export default PublicAssetCard;
