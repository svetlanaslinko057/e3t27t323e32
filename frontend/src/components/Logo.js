import { useTheme } from '@/contexts/ThemeContext';

/**
 * Lumen — brand mark.
 *
 * Uses the user-provided transparent PNGs verbatim — no pixel modification,
 * no plaque, no border, no theme inversion tricks. The PNG itself ships with
 * a transparent background and adapts via two variants:
 *
 *   • lumen-dark.png  — dark wordmark, for LIGHT theme surfaces
 *   • lumen-light.png — light/cream wordmark, for DARK theme surfaces
 *
 * `height` matches the original EVA-X sizing convention.
 */
export default function Logo({
  className = '',
  height = 44,
  alt = 'Lumen',
  testId = 'app-logo',
  // legacy prop from the SVG version (no-op, the image always includes the wordmark)
  // eslint-disable-next-line no-unused-vars
  showText = true,
}) {
  const { theme } = useTheme();
  const base = process.env.PUBLIC_URL || '';
  const src =
    theme === 'light'
      ? `${base}/branding/lumen-dark.v4.png`
      : `${base}/branding/lumen-light.v4.png`;
  return (
    <img
      data-testid={testId}
      src={src}
      alt={alt}
      draggable={false}
      style={{
        height,
        width: 'auto',
        maxWidth: '100%',
        objectFit: 'contain',
        display: 'block',
      }}
      className={className}
    />
  );
}
