/**
 * Manager · Investor Funnel — F1 (scoped to own assigned leads)
 * Hides manager- and funding-attribution sections (those are admin-only).
 */
import FunnelDashboardView from '@/components/FunnelDashboardView';

export default function ManagerFunnel() {
  return <FunnelDashboardView scope="manager" />;
}
