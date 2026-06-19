/**
 * Admin · Investor Funnel — F1
 * Global scope (sees all journeys + manager attribution + funding attribution).
 */
import FunnelDashboardView from '@/components/FunnelDashboardView';

export default function AdminFunnel() {
  return <FunnelDashboardView scope="admin" />;
}
