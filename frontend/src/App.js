import { useEffect, useState, useCallback, lazy, Suspense } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import axios from "axios";
import { createContext, useContext } from "react";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { getDeviceFingerprint } from "@/lib/deviceFingerprint";

import { ToastProvider } from "@/components/Toast";
import ToastBridgeMount from "@/components/ToastBridgeMount";
import RootErrorBoundary from "@/components/RootErrorBoundary";
import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";
import { LegalSettingsProvider } from "@/contexts/LegalSettingsContext";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { ContactModalProvider } from "@/contexts/ContactModalContext";
import { WalletProvider } from "@/contexts/WalletContext";
import { PublicWalletProvider } from "@/contexts/PublicWalletContext";
import { lumen } from "@/lib/lumenApi";
import { getClaim, clearClaim } from "@/lib/otcClaim";
import CookieBanner from "@/components/CookieBanner";
import EvaCompanion from "@/components/EvaCompanion";
import ActivityTrackerMount from "@/components/ActivityTrackerMount";

import LandingPage from "@/pages/LandingPage";
import PublicLayout from "@/layouts/PublicLayout";
const PublicHowPage = lazy(() => import("@/pages/public/PublicHowPage"));
const PublicAssetsPage = lazy(() => import("@/pages/public/PublicAssetsPage"));
const PublicCalculatorPage = lazy(() => import("@/pages/public/PublicCalculatorPage"));
const PublicContactsPage = lazy(() => import("@/pages/public/PublicContactsPage"));
const PublicAssetDetail = lazy(() => import("@/pages/PublicAssetDetail"));
const LegalIndexPage = lazy(() => import("@/pages/legal/LegalIndexPage"));
const LegalDocPage = lazy(() => import("@/pages/legal/LegalDocPage"));
import UnifiedAuthPage from "@/pages/UnifiedAuthPage";
import AdminLoginPage from "@/pages/AdminLoginPage";
const TwoFactorChallengePage = lazy(() => import("@/pages/TwoFactorChallengePage"));
const TwoFactorSetupPage = lazy(() => import("@/pages/TwoFactorSetupPage"));
const TwoFactorRecoveryPage = lazy(() => import("@/pages/TwoFactorRecoveryPage"));
const MobileAppPage = lazy(() => import("@/pages/MobileAppPage"));

import InvestorLayout from "@/layouts/InvestorLayout";
const InvestorDashboard = lazy(() => import("@/pages/investor/InvestorDashboard"));
const InvestorPortfolio = lazy(() => import("@/pages/investor/InvestorPortfolio"));
const InvestorOpportunities = lazy(() => import("@/pages/investor/InvestorOpportunities"));
const InvestorAssetDetail = lazy(() => import("@/pages/investor/InvestorAssetDetail"));
const InvestorPayments = lazy(() => import("@/pages/investor/InvestorPayments"));
const InvestorWallet = lazy(() => import("@/pages/investor/InvestorWallet"));
const InvestorRails = lazy(() => import("@/pages/investor/InvestorRails"));
const InvestorFunding = lazy(() => import("@/pages/investor/InvestorFunding"));
const InvestorIncome = lazy(() => import("@/pages/investor/InvestorIncome"));
const InvestorAnalytics = lazy(() => import("@/pages/investor/InvestorAnalytics"));
const InvestorContracts = lazy(() => import("@/pages/investor/InvestorContracts"));
const InvestorDocuments = lazy(() => import("@/pages/investor/InvestorDocuments"));
const InvestorProfile = lazy(() => import("@/pages/investor/InvestorProfile"));
const InvestorAccreditation = lazy(() => import("@/pages/investor/InvestorAccreditation"));
const InvestorCompliance = lazy(() => import("@/pages/investor/InvestorCompliance"));
const InvestorNotifications = lazy(() => import("@/pages/investor/InvestorNotifications"));
const InvestorNotificationPreferences = lazy(() => import("@/pages/investor/InvestorNotificationPreferences"));
const InvestorMarketplace = lazy(() => import("@/pages/investor/InvestorMarketplace"));
const LiquidityCenter = lazy(() => import("@/pages/investor/LiquidityCenter"));
const AdminSecondaryMarket = lazy(() => import("@/pages/admin/AdminSecondaryMarket"));
const AdminCryptoOS = lazy(() => import("@/pages/admin/AdminCryptoOS"));
const AdminMarketMakers = lazy(() => import("@/pages/admin/AdminMarketMakers"));

import AdminLayout from "@/layouts/AdminLayout";
const AdminDashboard = lazy(() => import("@/pages/admin/AdminDashboard"));
const AdminInvestors = lazy(() => import("@/pages/admin/AdminInvestors"));
const AdminIntents = lazy(() => import("@/pages/admin/AdminIntents"));
const AdminKyc = lazy(() => import("@/pages/admin/AdminKyc"));
const AdminAccreditation = lazy(() => import("@/pages/admin/AdminAccreditation"));
const AdminInvestorRelations = lazy(() => import("@/pages/admin/AdminInvestorRelations"));
const AdminManagerOps = lazy(() => import("@/pages/admin/AdminManagerOps"));
const AdminStaffSecurity = lazy(() => import("@/pages/admin/AdminStaffSecurity"));
const AdminAssets = lazy(() => import("@/pages/admin/AdminAssets"));
const AdminAssetEditor = lazy(() => import("@/pages/admin/AdminAssetEditor"));
const AdminAssetContent = lazy(() => import("@/pages/admin/AdminAssetContent"));
const AdminQuestions = lazy(() => import("@/pages/admin/AdminQuestions"));
const AdminRounds = lazy(() => import("@/pages/admin/AdminRounds"));
const AdminPayments = lazy(() => import("@/pages/admin/AdminPayments"));
const AdminWithdrawals = lazy(() => import("@/pages/admin/AdminWithdrawals"));
const AdminPayouts = lazy(() => import("@/pages/admin/AdminPayouts"));
const AdminFinanceEngine = lazy(() => import("@/pages/admin/AdminFinanceEngine"));
const AdminFundIntelligence = lazy(() => import("@/pages/admin/AdminFundIntelligence"));
const AdminFundingAccounts = lazy(() => import("@/pages/admin/AdminFundingAccounts"));
const AdminLedger = lazy(() => import("@/pages/admin/AdminLedger"));
const AdminContracts = lazy(() => import("@/pages/admin/AdminContracts"));
const AdminDocuments = lazy(() => import("@/pages/admin/AdminDocuments"));
const AdminReports = lazy(() => import("@/pages/admin/AdminReports"));
const AdminSettings = lazy(() => import("@/pages/admin/AdminSettings"));
const AdminSystemHealth = lazy(() => import("@/pages/admin/AdminSystemHealth"));
const AdminAuditLog = lazy(() => import("@/pages/admin/AdminAuditLog"));
const AdminBankTransactions = lazy(() => import("@/pages/admin/AdminBankTransactions"));
const AdminBankReconciliation = lazy(() => import("@/pages/admin/AdminBankReconciliation"));
const AdminRailsOps = lazy(() => import("@/pages/admin/AdminRailsOps"));
const AdminPayoutExport = lazy(() => import("@/pages/admin/AdminPayoutExport"));
const AdminOperations = lazy(() => import("@/pages/admin/AdminOperations"));
const AdminSOP = lazy(() => import("@/pages/admin/AdminSOP"));
const AdminUnitRegistry = lazy(() => import("@/pages/admin/AdminUnitRegistry"));
const AdminCertificates = lazy(() => import("@/pages/admin/AdminCertificates"));
const InvestorUnits = lazy(() => import("@/pages/investor/InvestorUnits"));
const InvestorCertificates = lazy(() => import("@/pages/investor/InvestorCertificates"));
const InvestorJourney = lazy(() => import("@/pages/investor/InvestorJourney"));
const CertificateVerifyPage = lazy(() => import("@/pages/CertificateVerifyPage"));
// Phase E — Capital Formation OS
const AdminCapitalPipeline = lazy(() => import("@/pages/admin/AdminCapitalPipeline"));
const AdminPipelineAnalytics = lazy(() => import("@/pages/admin/AdminPipelineAnalytics"));
const AdminOperators = lazy(() => import("@/pages/admin/AdminOperators"));
const AdminInvestorSegments = lazy(() => import("@/pages/admin/AdminInvestorSegments"));
const InvestorCommitments = lazy(() => import("@/pages/investor/InvestorCommitments"));
// Phase F — Operator OS
import OperatorLayout from "@/layouts/OperatorLayout";
const OperatorDashboard = lazy(() => import("@/pages/operator/OperatorDashboard"));
const OperatorAssets = lazy(() => import("@/pages/operator/OperatorAssets"));
const OperatorReports = lazy(() => import("@/pages/operator/OperatorReports"));
const OperatorInvestors = lazy(() => import("@/pages/operator/OperatorInvestors"));
const OperatorSla = lazy(() => import("@/pages/operator/OperatorSla"));
const OperatorFees = lazy(() => import("@/pages/operator/OperatorFees"));
const OperatorLeaderboard = lazy(() => import("@/pages/OperatorLeaderboard"));
// Phase G — Institutional Ownership OS
import InstitutionalLayout from "@/layouts/InstitutionalLayout";
const InstitutionalDashboard = lazy(() => import("@/pages/institutional/InstitutionalDashboard"));
const InstitutionalFunds = lazy(() => import("@/pages/institutional/InstitutionalFunds"));
const FundDetail = lazy(() => import("@/pages/institutional/FundDetail"));
const InstitutionalSyndicates = lazy(() => import("@/pages/institutional/InstitutionalSyndicates"));
const InstitutionalStructure = lazy(() => import("@/pages/institutional/InstitutionalStructure"));
const InstitutionalCompliance = lazy(() => import("@/pages/institutional/InstitutionalCompliance"));
const InstitutionalUbo = lazy(() => import("@/pages/institutional/InstitutionalUbo"));
const InstitutionalGovernance = lazy(() => import("@/pages/institutional/InstitutionalGovernance"));
const AdminFunds = lazy(() => import("@/pages/admin/AdminFunds"));
const AdminSyndicates = lazy(() => import("@/pages/admin/AdminSyndicates"));
const AdminUbo = lazy(() => import("@/pages/admin/AdminUbo"));
const AdminCompliance = lazy(() => import("@/pages/admin/AdminCompliance"));
const AdminComplianceScreening = lazy(() => import("@/pages/admin/AdminComplianceScreening"));
const AdminGovernance = lazy(() => import("@/pages/admin/AdminGovernance"));
const AdminTrustGraph = lazy(() => import("@/pages/admin/AdminTrustGraph"));
// Phase G12/G13/G14 — Reporting + LP/GP + Audit Explorer
const AdminAuditExplorer = lazy(() => import("@/pages/admin/AdminAuditExplorer"));
const AdminReportBuilder = lazy(() => import("@/pages/admin/AdminReportBuilder"));
const AdminFundLpgp = lazy(() => import("@/pages/admin/AdminFundLpgp"));
// Phase LR2 — Launch Readiness 2.0 + Institutional Overview
const AdminLaunchReadiness = lazy(() => import("@/pages/admin/AdminLaunchReadiness"));
const AdminPools = lazy(() => import("@/pages/admin/AdminPools"));
const AdminTreasury = lazy(() => import("@/pages/admin/AdminTreasury"));
const AdminInstitutionalOverview = lazy(() => import("@/pages/admin/AdminInstitutionalOverview"));
const AdminCommandCenter = lazy(() => import("@/pages/admin/AdminCommandCenter"));
const InvestorTimeline = lazy(() => import("@/pages/investor/InvestorTimeline"));
const InvestorReports = lazy(() => import("@/pages/investor/InvestorReports"));
const InvestorLpDashboard = lazy(() => import("@/pages/investor/InvestorLpDashboard"));
const InvestorPools = lazy(() => import("@/pages/investor/InvestorPools"));
const InvestorCryptoCenter = lazy(() => import("@/pages/investor/InvestorCryptoCenter"));
const InvestorAssets = lazy(() => import("@/pages/investor/InvestorAssets"));
const InvestorOtcMarket = lazy(() => import("@/pages/investor/InvestorOtcMarket"));
const InvestorOtcLot = lazy(() => import("@/pages/investor/InvestorOtcLot"));

// Public OTC marketplace (standalone pages, no auth required to browse/reserve)
const OtcMarketPage = lazy(() => import("@/pages/otc/OtcMarketPage"));
const OtcLotPage = lazy(() => import("@/pages/otc/OtcLotPage"));

// Manager cabinet (IR2 Layer B — Manager OS UI)
import ManagerLayout from "@/layouts/ManagerLayout";
const ManagerDashboard = lazy(() => import("@/pages/manager/ManagerDashboard"));
const ManagerLeads = lazy(() => import("@/pages/manager/ManagerLeads"));
const ManagerPipeline = lazy(() => import("@/pages/manager/ManagerPipeline"));
const ManagerActivity = lazy(() => import("@/pages/manager/ManagerActivity"));

// Phase S1 — SEO Surface + Public Contract View Token
const PublicContractView = lazy(() => import("@/pages/PublicContractView"));
const AdminSeoSettings = lazy(() => import("@/pages/admin/AdminSeoSettings"));

// F1 — Investor Funnel Analytics
const AdminFunnel = lazy(() => import("@/pages/admin/AdminFunnel"));
const AdminSiteActivity = lazy(() => import("@/pages/admin/AdminSiteActivity"));
const AdminCommChannels = lazy(() => import("@/pages/admin/AdminCommChannels"));
const AdminManagerInstructions = lazy(() => import("@/pages/admin/AdminManagerInstructions"));
const ManagerFunnel = lazy(() => import("@/pages/manager/ManagerFunnel"));
const ManagerInstructions = lazy(() => import("@/pages/manager/ManagerInstructions"));

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
export const API = `${BACKEND_URL}/api`;

import { runtime } from '@/runtime';
const _runtimeBootPromise = Promise.race([
  runtime.capabilities.refresh().catch(() => null),
  new Promise((res) => setTimeout(res, 1500)),
]);
export const runtimeReady = _runtimeBootPromise;

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/auth/me`, { withCredentials: true });
      setUser(response.data);
    } catch (error) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  const login = async (email, password) => {
    const response = await axios.post(
      `${API}/auth/login`,
      { email, password, device_fingerprint: getDeviceFingerprint() },
      { withCredentials: true }
    );
    if (response.data?.requires_2fa) {
      const err = new Error('TwoFactorRequired');
      err.requires_2fa = true;
      err.challenge_token = response.data.challenge_token;
      err.method = response.data.method || 'totp';
      err.ttl_seconds = response.data.ttl_seconds;
      err.email = email;
      throw err;
    }
    setUser(response.data);
    return response.data;
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/auth/logout`, {}, { withCredentials: true });
    } catch (error) { /* ignore */ }
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
};

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4">
        <div className="w-10 h-10 border-2 border-border border-t-[#2E5D4F] rounded-full animate-spin" />
        <p className="text-sm text-muted-foreground">Перевіряємо сесію…</p>
      </div>
    );
  }

  if (!user) {
    if (location.pathname.startsWith('/admin')) {
      return <Navigate to="/admin/login" state={{ from: location }} replace />;
    }
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    const dashboardRoutes = {
      client: '/investor/dashboard',
      investor: '/investor/dashboard',
      admin: '/admin/command-center',
      operator: '/manager/dashboard',
      manager: '/manager/dashboard',
    };
    return <Navigate to={dashboardRoutes[user.role] || '/investor/dashboard'} replace />;
  }

  return children;
};

const LoadingFallback = () => (
  <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4" data-testid="route-loading">
    <div className="w-10 h-10 border-2 border-border border-t-[#2E5D4F] rounded-full animate-spin" />
    <p className="text-sm text-muted-foreground">Завантаження…</p>
  </div>
);

/**
 * After a guest who reserved an OTC lot logs in/registers, automatically CLAIM
 * the reservation so the bought lot shows up in their cabinet. Runs once per
 * authenticated session when a pending claim token exists in localStorage.
 */
function OtcClaimOnAuth() {
  const { user } = useAuth();
  useEffect(() => {
    if (!user) return;
    const c = getClaim();
    if (!c || !c.token || c.token === '__pending__') return;
    lumen.post('/investor/otc/claim', { claim_token: c.token })
      .then(() => clearClaim())
      .catch(() => { /* keep token; manager flow can reconcile later */ });
  }, [user]);
  return null;
}

function AppRouter() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <Routes>
        {/* ── Public marketing site (shared shell: header + overlay menu + giant footer) ── */}
        <Route element={<PublicLayout />}>
          <Route path="/" element={<LandingPage />} />
          <Route path="/how" element={<PublicHowPage />} />
          <Route path="/assets" element={<PublicAssetsPage />} />
          <Route path="/calculator" element={<PublicCalculatorPage />} />
          <Route path="/contacts" element={<PublicContactsPage />} />
          <Route path="/objects/:id" element={<PublicAssetDetail />} />
          <Route path="/app" element={<MobileAppPage />} />
          {/* Public OTC marketplace — standalone pages */}
          <Route path="/otc" element={<OtcMarketPage />} />
          <Route path="/otc/:id" element={<OtcLotPage />} />
        </Route>

        <Route path="/legal" element={<LegalIndexPage />} />
        <Route path="/legal/:slug" element={<LegalDocPage />} />
        <Route path="/certificates/verify" element={<CertificateVerifyPage />} />
        <Route path="/certificates/verify/:code" element={<CertificateVerifyPage />} />
        <Route path="/operators/leaderboard" element={<OperatorLeaderboard />} />

        {/* Phase S1.2 — Public Contract View Token (no auth required) */}
        <Route path="/c/view/:token" element={<PublicContractView />} />
        <Route path="/contracts/view/:token" element={<PublicContractView />} />

        <Route path="/auth" element={<UnifiedAuthPage />} />

        <Route path="/mobile" element={<Navigate to="/app" replace />} />
        <Route path="/login" element={<Navigate to="/auth" replace />} />
        <Route path="/register" element={<Navigate to="/auth?mode=register" replace />} />
        <Route path="/client/auth" element={<Navigate to="/auth" replace />} />
        <Route path="/builder/auth" element={<Navigate to="/auth" replace />} />
        <Route path="/auth/client" element={<Navigate to="/auth" replace />} />
        <Route path="/auth/builder" element={<Navigate to="/auth" replace />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />

        <Route path="/two-factor-challenge" element={<TwoFactorChallengePage />} />
        <Route path="/account/2fa/setup" element={<ProtectedRoute><TwoFactorSetupPage /></ProtectedRoute>} />
        <Route path="/account/2fa/recovery" element={<ProtectedRoute><TwoFactorRecoveryPage /></ProtectedRoute>} />
        <Route path="/account/2fa" element={<Navigate to="/account/2fa/recovery" replace />} />

        {/* Investor cabinet */}
        <Route
          path="/investor"
          element={
            <ProtectedRoute allowedRoles={['client', 'investor', 'admin']}>
              <InvestorLayout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<InvestorDashboard />} />
          <Route path="portfolio" element={<InvestorPortfolio />} />
          <Route path="opportunities" element={<InvestorOpportunities />} />
          <Route path="assets" element={<Navigate to="/investor/opportunities" replace />} />
          <Route path="assets/:assetId" element={<InvestorAssetDetail />} />
          <Route path="payments" element={<InvestorPayments />} />
          <Route path="wallet" element={<InvestorWallet />} />
          <Route path="rails" element={<InvestorRails />} />
          <Route path="funding" element={<InvestorFunding />} />
          <Route path="income" element={<InvestorIncome />} />
          <Route path="analytics" element={<InvestorAnalytics />} />
          <Route path="contracts" element={<InvestorContracts />} />
          <Route path="documents" element={<InvestorDocuments />} />
          <Route path="profile" element={<InvestorProfile />} />
          <Route path="accreditation" element={<InvestorAccreditation />} />
          <Route path="compliance" element={<InvestorCompliance />} />
          <Route path="notifications" element={<InvestorNotifications />} />
          <Route path="notification-preferences" element={<InvestorNotificationPreferences />} />
          <Route path="marketplace" element={<InvestorMarketplace />} />
          <Route path="liquidity" element={<LiquidityCenter />} />
          <Route path="units" element={<InvestorUnits />} />
          <Route path="certificates" element={<InvestorCertificates />} />
          <Route path="journey" element={<InvestorJourney />} />
          <Route path="commitments" element={<InvestorCommitments />} />
          <Route path="timeline" element={<InvestorTimeline />} />
          <Route path="reports" element={<InvestorReports />} />
          <Route path="lp-funds" element={<InvestorLpDashboard />} />
          <Route path="pools" element={<InvestorPools />} />
          <Route path="crypto" element={<InvestorCryptoCenter />} />
          <Route path="my-assets" element={<InvestorAssets />} />
          <Route path="otc" element={<InvestorOtcMarket />} />
          <Route path="otc/:id" element={<InvestorOtcLot />} />
          <Route index element={<Navigate to="/investor/dashboard" replace />} />
        </Route>

        {/* Legacy /client/* → /investor/* */}
        <Route path="/client" element={<Navigate to="/investor/dashboard" replace />} />
        <Route path="/client/dashboard" element={<Navigate to="/investor/dashboard" replace />} />
        <Route path="/client/projects" element={<Navigate to="/investor/portfolio" replace />} />
        <Route path="/client/documents" element={<Navigate to="/investor/documents" replace />} />
        <Route path="/client/profile" element={<Navigate to="/investor/profile" replace />} />
        <Route path="/client/*" element={<Navigate to="/investor/dashboard" replace />} />

        {/* Old roles → landing */}
        <Route path="/developer/*" element={<Navigate to="/" replace />} />
        <Route path="/tester/*" element={<Navigate to="/" replace />} />
        <Route path="/provider/*" element={<Navigate to="/" replace />} />
        <Route path="/dev/*" element={<Navigate to="/" replace />} />

        {/* Manager cabinet (IR2 Layer B — Manager OS UI) */}
        <Route
          path="/manager"
          element={
            <ProtectedRoute allowedRoles={['manager', 'operator', 'admin']}>
              <ManagerLayout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<ManagerDashboard />} />
          <Route path="leads" element={<ManagerLeads />} />
          <Route path="pipeline" element={<ManagerPipeline />} />
          <Route path="activity" element={<ManagerActivity />} />
          {/* F1 — Investor Funnel (manager scope) */}
          <Route path="funnel" element={<ManagerFunnel />} />
          {/* F4 — Manager Instructions (read + acknowledge) */}
          <Route path="instructions" element={<ManagerInstructions />} />
          {/* Operator OS (merged into the unified Manager cabinet) */}
          <Route path="assets" element={<OperatorAssets />} />
          <Route path="reports" element={<OperatorReports />} />
          <Route path="sla" element={<OperatorSla />} />
          <Route path="asset-investors" element={<OperatorInvestors />} />
          <Route path="fees" element={<OperatorFees />} />
          <Route index element={<Navigate to="/manager/dashboard" replace />} />
        </Route>

        {/* Operator portal — merged into the Manager cabinet; redirect legacy paths */}
        <Route path="/operator" element={<Navigate to="/manager/dashboard" replace />} />
        <Route path="/operator/dashboard" element={<Navigate to="/manager/dashboard" replace />} />
        <Route path="/operator/assets" element={<Navigate to="/manager/assets" replace />} />
        <Route path="/operator/reports" element={<Navigate to="/manager/reports" replace />} />
        <Route path="/operator/sla" element={<Navigate to="/manager/sla" replace />} />
        <Route path="/operator/investors" element={<Navigate to="/manager/asset-investors" replace />} />
        <Route path="/operator/fees" element={<Navigate to="/manager/fees" replace />} />

        {/* Institutional Ownership OS (Phase G) — gated server-side by segment */}
        <Route
          path="/institutional"
          element={
            <ProtectedRoute allowedRoles={['client', 'investor', 'admin', 'operator']}>
              <InstitutionalLayout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<InstitutionalDashboard />} />
          <Route path="funds" element={<InstitutionalFunds />} />
          <Route path="funds/:fundId" element={<FundDetail />} />
          <Route path="syndicates" element={<InstitutionalSyndicates />} />
          <Route path="structure" element={<InstitutionalStructure />} />
          <Route path="compliance" element={<InstitutionalCompliance />} />
          <Route path="governance" element={<InstitutionalGovernance />} />
          <Route path="ubo" element={<InstitutionalUbo />} />
          <Route index element={<Navigate to="/institutional/dashboard" replace />} />
        </Route>

        {/* Admin */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminLayout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<AdminDashboard />} />
          <Route path="operations" element={<AdminOperations />} />
          <Route path="registry" element={<AdminUnitRegistry />} />
          <Route path="certificates" element={<AdminCertificates />} />
          <Route path="sop" element={<AdminSOP />} />
          <Route path="investors" element={<AdminInvestors />} />
          <Route path="intents" element={<AdminIntents />} />
          <Route path="kyc" element={<AdminKyc />} />
          <Route path="accreditation" element={<AdminAccreditation />} />
          <Route path="assets" element={<AdminAssets />} />
          <Route path="assets/new" element={<AdminAssetEditor />} />
          <Route path="assets/:assetId" element={<AdminAssetEditor />} />
          <Route path="assets/:assetId/content" element={<AdminAssetContent />} />
          <Route path="questions" element={<AdminQuestions />} />
          <Route path="rounds" element={<AdminRounds />} />
          <Route path="payments" element={<AdminPayments />} />
          <Route path="withdrawals" element={<AdminWithdrawals />} />
          <Route path="payouts" element={<AdminPayouts />} />
          <Route path="finance-engine" element={<AdminFinanceEngine />} />
          <Route path="fund" element={<AdminFundIntelligence />} />
          <Route path="funding-accounts" element={<AdminFundingAccounts />} />
          <Route path="ledger" element={<AdminLedger />} />
          <Route path="contracts" element={<AdminContracts />} />
          <Route path="documents" element={<AdminDocuments />} />
          <Route path="reports" element={<AdminReports />} />
          <Route path="settings" element={<AdminSettings />} />
          <Route path="system-health" element={<AdminSystemHealth />} />
          <Route path="audit-log" element={<AdminAuditLog />} />
          <Route path="bank-transactions" element={<AdminBankTransactions />} />
          <Route path="bank-reconciliation" element={<AdminBankReconciliation />} />
          <Route path="rails" element={<AdminRailsOps />} />
          <Route path="treasury" element={<AdminTreasury />} />
          <Route path="payout-export" element={<AdminPayoutExport />} />
          <Route path="secondary-market" element={<AdminSecondaryMarket />} />
          <Route path="web3" element={<AdminCryptoOS />} />
          <Route path="market-makers" element={<AdminMarketMakers />} />
          {/* Phase E — Capital Formation OS */}
          <Route path="pipeline" element={<AdminCapitalPipeline />} />
          <Route path="pipeline-analytics" element={<AdminPipelineAnalytics />} />
          <Route path="operators" element={<AdminOperators />} />
          <Route path="investor-segments" element={<AdminInvestorSegments />} />
          <Route path="funds" element={<AdminFunds />} />
          <Route path="syndicates" element={<AdminSyndicates />} />
          <Route path="ubo" element={<AdminUbo />} />
          <Route path="compliance" element={<AdminCompliance />} />
          <Route path="compliance-screening" element={<AdminComplianceScreening />} />
          <Route path="governance" element={<AdminGovernance />} />
          <Route path="trust-graph" element={<AdminTrustGraph />} />
          <Route path="audit-explorer" element={<AdminAuditExplorer />} />
          <Route path="report-builder" element={<AdminReportBuilder />} />
          <Route path="fund-lpgp" element={<AdminFundLpgp />} />
          <Route path="launch-readiness" element={<AdminLaunchReadiness />} />
          <Route path="pools" element={<AdminPools />} />
          <Route path="institutional-overview" element={<AdminInstitutionalOverview />} />
          {/* Phase H1.3 — Controlled Beta Command Center */}
          <Route path="command-center" element={<AdminCommandCenter />} />
          {/* Phase IR1 — Investor Relations OS */}
          <Route path="investor-relations" element={<AdminInvestorRelations />} />
          {/* Manager OS Completion (M5–M7) — Team control + Security */}
          <Route path="manager-ops" element={<AdminManagerOps />} />
          <Route path="staff-security" element={<AdminStaffSecurity />} />
          {/* Phase S1.1 — SEO Surface (master-admin) */}
          <Route path="seo-settings" element={<AdminSeoSettings />} />
          {/* F1 — Investor Funnel Analytics */}
          <Route path="funnel" element={<AdminFunnel />} />
          {/* F2 — Site Activity Layer */}
          <Route path="site-activity" element={<AdminSiteActivity />} />
          {/* F5 — Communication Provider Layer */}
          <Route path="comm-channels" element={<AdminCommChannels />} />
          {/* F4 — Manager Instructions (authoring) */}
          <Route path="manager-instructions" element={<AdminManagerInstructions />} />
          {/* legacy admin paths */}
          <Route path="workflow" element={<Navigate to="/admin/assets" replace />} />
          <Route path="finance" element={<Navigate to="/admin/payments" replace />} />
          <Route path="team" element={<Navigate to="/admin/investors" replace />} />
          <Route path="system" element={<Navigate to="/admin/settings" replace />} />
          <Route path="profile" element={<Navigate to="/admin/settings" replace />} />
          <Route path="qa" element={<Navigate to="/admin/dashboard" replace />} />
          <Route path="validation" element={<Navigate to="/admin/dashboard" replace />} />
          <Route path="leads" element={<Navigate to="/admin/investors" replace />} />
          <Route path="marketing" element={<Navigate to="/admin/dashboard" replace />} />
          <Route path="portfolio" element={<Navigate to="/admin/assets" replace />} />
          <Route path="legal-settings" element={<Navigate to="/admin/settings" replace />} />
          <Route index element={<Navigate to="/admin/command-center" replace />} />
        </Route>

        <Route path="/dashboard" element={<Navigate to="/investor/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

function CookieBannerMount() {
  const { theme } = useTheme();
  const location = useLocation();
  // Inside the authenticated cabinets the left sidebar holds the logout/profile
  // control at the bottom-left — offset the banner so it never overlaps it.
  const inApp = /^\/(investor|admin|operator|institutional)(\/|$)/.test(location.pathname);
  return <CookieBanner tone={theme === 'light' ? 'light' : 'dark'} inApp={inApp} />;
}

function App() {
  const googleClientId = process.env.REACT_APP_GOOGLE_CLIENT_ID || "";
  return (
    <div className="App">
      <GoogleOAuthProvider clientId={googleClientId}>
        <BrowserRouter basename={process.env.PUBLIC_URL || ""}>
          <ThemeProvider>
            <LanguageProvider>
              <LegalSettingsProvider>
                <AuthProvider>
                  <WalletProvider>
                  <PublicWalletProvider>
                  <ToastProvider>
                    <ToastBridgeMount />
                    <ActivityTrackerMount />
                    <OtcClaimOnAuth />
                    <ContactModalProvider>
                      <RootErrorBoundary>
                        <AppRouter />
                      </RootErrorBoundary>
                    </ContactModalProvider>
                    <CookieBannerMount />
                    <EvaCompanion />
                  </ToastProvider>
                  </PublicWalletProvider>
                  </WalletProvider>
                </AuthProvider>
              </LegalSettingsProvider>
            </LanguageProvider>
          </ThemeProvider>
        </BrowserRouter>
      </GoogleOAuthProvider>
    </div>
  );
}

export default App;
