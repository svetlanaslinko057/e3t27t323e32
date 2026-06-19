/**
 * LumenSelect — Lumen's canonical select control.
 * Built on Radix Select for accessibility, styled with Lumen visual language.
 */
import * as React from 'react';
import {
  Root as RSRoot,
  Trigger as RSTrigger,
  Value as RSValue,
  Icon as RSIcon,
  Portal as RSPortal,
  Content as RSContent,
  Viewport as RSViewport,
  ScrollUpButton as RSScrollUpButton,
  ScrollDownButton as RSScrollDownButton,
  Item as RSItem,
  ItemText as RSItemText,
  ItemIndicator as RSItemIndicator,
  Separator as RSSeparator,
  Group as RSGroup,
  Label as RSLabel,
} from '@radix-ui/react-select';
import { Check, ChevronDown, ChevronUp } from 'lucide-react';

const cn = (...c) => c.filter(Boolean).join(' ');

const SIZE_STYLES = {
  sm: 'h-9 text-sm px-3',
  md: 'h-10 text-sm px-3.5',
  lg: 'h-12 text-base px-4',
};

function LumenSelectRoot({
  value,
  defaultValue,
  onValueChange,
  placeholder = 'Виберіть…',
  options,
  size = 'md',
  disabled,
  className,
  align = 'start',
  testid,
  label,
  helper,
  error,
  children,
}) {
  const sizeCls = SIZE_STYLES[size] || SIZE_STYLES.md;
  return (
    <div className={cn('w-full', className)}>
      {label && (
        <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1.5 font-semibold">
          {label}
        </label>
      )}
      <RSRoot value={value} defaultValue={defaultValue} onValueChange={onValueChange} disabled={disabled}>
        <RSTrigger
          data-testid={testid}
          aria-invalid={!!error}
          className={cn(
            'group inline-flex w-full items-center justify-between gap-2 rounded-xl border bg-card text-foreground transition-colors',
            'shadow-[0_1px_0_rgba(0,0,0,0.02)]',
            sizeCls,
            error
              ? 'border-rose-300 focus:outline-none focus:ring-2 focus:ring-rose-400/40 focus:border-rose-400'
              : 'border-border hover:border-amber-300 focus:outline-none focus:ring-2 focus:ring-amber-400/40 focus:border-amber-400',
            disabled && 'opacity-50 cursor-not-allowed',
          )}
        >
          <RSValue placeholder={placeholder} />
          <RSIcon asChild>
            <ChevronDown className="w-4 h-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
          </RSIcon>
        </RSTrigger>

        <RSPortal>
          <RSContent
            position="popper"
            sideOffset={6}
            align={align}
            className={cn(
              'z-50 min-w-[var(--radix-select-trigger-width)] overflow-hidden',
              'rounded-xl border border-border bg-popover text-popover-foreground shadow-xl',
              'backdrop-blur-sm',
              'data-[state=open]:animate-in data-[state=closed]:animate-out',
              'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
              'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
            )}
          >
            <RSScrollUpButton className="flex items-center justify-center h-6 cursor-default">
              <ChevronUp className="w-3.5 h-3.5" />
            </RSScrollUpButton>
            <RSViewport className="p-1.5 max-h-72">
              {options
                ? options.map((opt) => (
                    <Item key={opt.value} value={opt.value} disabled={opt.disabled}>
                      <div className="flex flex-col">
                        <span>{opt.label}</span>
                        {opt.hint && <span className="text-[11px] text-muted-foreground">{opt.hint}</span>}
                      </div>
                    </Item>
                  ))
                : children}
            </RSViewport>
            <RSScrollDownButton className="flex items-center justify-center h-6 cursor-default">
              <ChevronDown className="w-3.5 h-3.5" />
            </RSScrollDownButton>
          </RSContent>
        </RSPortal>
      </RSRoot>
      {helper && !error && (
        <p className="mt-1 text-[11px] text-muted-foreground">{helper}</p>
      )}
      {error && (
        <p className="mt-1 text-[11px] text-rose-600 dark:text-rose-400">{error}</p>
      )}
    </div>
  );
}

const Item = React.forwardRef(function Item({ children, value, disabled, className }, ref) {
  return (
    <RSItem
      ref={ref}
      value={value}
      disabled={disabled}
      className={cn(
        'relative flex w-full select-none items-center justify-between gap-2 cursor-pointer',
        'px-3 py-2 rounded-lg text-sm outline-none transition-colors',
        'data-[highlighted]:bg-amber-50 dark:data-[highlighted]:bg-amber-950/40',
        'data-[highlighted]:text-amber-900 dark:data-[highlighted]:text-amber-100',
        'data-[disabled]:opacity-40 data-[disabled]:cursor-not-allowed',
        'data-[state=checked]:font-semibold',
        className,
      )}
    >
      <RSItemText>{children}</RSItemText>
      <RSItemIndicator>
        <Check className="w-4 h-4 text-amber-600 dark:text-amber-400" />
      </RSItemIndicator>
    </RSItem>
  );
});

const Separator = () => (
  <RSSeparator className="my-1 h-px bg-border" />
);

const Group = ({ label, children }) => (
  <RSGroup>
    {label && (
      <RSLabel className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
        {label}
      </RSLabel>
    )}
    {children}
  </RSGroup>
);

LumenSelectRoot.Item = Item;
LumenSelectRoot.Separator = Separator;
LumenSelectRoot.Group = Group;

export default LumenSelectRoot;
export { LumenSelectRoot as LumenSelect, Item as LumenSelectItem, Separator as LumenSelectSeparator, Group as LumenSelectGroup };
