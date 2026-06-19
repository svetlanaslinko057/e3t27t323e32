/**
 * Editorial kicker / section label with a short rule. Mono-uppercase.
 */
export const SectionLabel = ({ children, tone = 'green', className = '' }) => {
  const color = tone === 'light' ? 'text-[#E5C98A]' : 'text-[#A98A45]';
  const rule = tone === 'light'
    ? 'bg-gradient-to-r from-[#E5C98A] to-transparent'
    : 'bg-gradient-to-r from-[#C9A961] to-[#E5C98A]';
  return (
    <p className={`inline-flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.22em] ${color} ${className}`} data-testid="section-label">
      <span className={`h-[2px] w-8 rounded-full ${rule}`} aria-hidden />
      {children}
    </p>
  );
};

export default SectionLabel;
