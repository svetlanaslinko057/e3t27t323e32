/**
 * Editorial kicker / section label with a short rule. Mono-uppercase.
 */
export const SectionLabel = ({ children, tone = 'green', className = '' }) => {
  const color = tone === 'light' ? 'text-white/70' : 'text-[#2E5D4F]';
  const rule = tone === 'light' ? 'bg-white/40' : 'bg-[#2E5D4F]';
  return (
    <p className={`inline-flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.22em] ${color} ${className}`} data-testid="section-label">
      <span className={`h-px w-7 ${rule}`} aria-hidden />
      {children}
    </p>
  );
};

export default SectionLabel;
