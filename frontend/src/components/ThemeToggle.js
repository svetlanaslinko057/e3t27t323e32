import { Sun, Moon } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';

/**
 * ThemeToggle — small icon button that flips between dark and light.
 * Uses semantic tokens so it adapts to the active theme.
 */
const ThemeToggle = ({ className = '' }) => {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      onClick={toggleTheme}
      className={`theme-toggle-btn relative group transition-all duration-200 ${className}`}
      style={{
        background: 'transparent',
        border: '0',
        padding: '6px',
        borderRadius: 8,
        color: 'var(--token-text-secondary)',
        cursor: 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        lineHeight: 1,
        minWidth: 32,
        minHeight: 32,
      }}
      data-testid="theme-toggle"
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Light mode' : 'Dark mode'}
    >
      <div className="relative w-4 h-4">
        <Sun
          className={`absolute inset-0 w-4 h-4 transition-all duration-300 ${
            isDark ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 rotate-90 scale-0'
          }`}
          style={{ color: 'var(--t-warning)' }}
        />
        <Moon
          className={`absolute inset-0 w-4 h-4 transition-all duration-300 ${
            !isDark ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 -rotate-90 scale-0'
          }`}
          style={{ color: 'var(--token-text-secondary)' }}
        />
      </div>
    </button>
  );
};

export default ThemeToggle;
