/**
 * MarkdownLite — tiny, dependency-free markdown renderer for legal/SOP bodies.
 *
 * Supports the subset our seed content uses:
 *   # / ## / ###      headings
 *   **bold**          inline bold
 *   - item            unordered list
 *   1. item           ordered list
 *   > callout         blockquote
 *   blank line        paragraph break
 *
 * Pure presentational. Inherits color from parent (`text-current`) so it works
 * on both the public (light/dark) and admin (token) surfaces.
 */
import React from 'react';

function renderInline(text, keyBase) {
  // Split on **bold** segments, keep delimiters.
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) {
      return (
        <strong key={`${keyBase}-b-${i}`} className="font-semibold text-current">
          {p.slice(2, -2)}
        </strong>
      );
    }
    return <React.Fragment key={`${keyBase}-t-${i}`}>{p}</React.Fragment>;
  });
}

export default function MarkdownLite({ text, className = '' }) {
  const lines = String(text || '').replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let list = null; // { type: 'ul'|'ol', items: [] }

  const flushList = () => {
    if (list) {
      blocks.push(list);
      list = null;
    }
  };

  lines.forEach((raw) => {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) {
      flushList();
      return;
    }
    let m;
    if ((m = line.match(/^###\s+(.*)$/))) { flushList(); blocks.push({ type: 'h3', text: m[1] }); return; }
    if ((m = line.match(/^##\s+(.*)$/)))  { flushList(); blocks.push({ type: 'h2', text: m[1] }); return; }
    if ((m = line.match(/^#\s+(.*)$/)))   { flushList(); blocks.push({ type: 'h1', text: m[1] }); return; }
    if ((m = line.match(/^>\s?(.*)$/)))   { flushList(); blocks.push({ type: 'quote', text: m[1] }); return; }
    if ((m = line.match(/^[-*]\s+(.*)$/))) {
      if (!list || list.type !== 'ul') { flushList(); list = { type: 'ul', items: [] }; }
      list.items.push(m[1]);
      return;
    }
    if ((m = line.match(/^\d+\.\s+(.*)$/))) {
      if (!list || list.type !== 'ol') { flushList(); list = { type: 'ol', items: [] }; }
      list.items.push(m[1]);
      return;
    }
    flushList();
    blocks.push({ type: 'p', text: line });
  });
  flushList();

  return (
    <div className={`markdown-lite text-current ${className}`}>
      {blocks.map((b, i) => {
        switch (b.type) {
          case 'h1':
            return <h1 key={i} className="text-2xl md:text-3xl font-bold tracking-tight mt-2 mb-4 text-current">{renderInline(b.text, `h1-${i}`)}</h1>;
          case 'h2':
            return <h2 key={i} className="text-lg md:text-xl font-bold tracking-tight mt-7 mb-2.5 text-current">{renderInline(b.text, `h2-${i}`)}</h2>;
          case 'h3':
            return <h3 key={i} className="text-base font-semibold mt-5 mb-2 text-current">{renderInline(b.text, `h3-${i}`)}</h3>;
          case 'quote':
            return (
              <blockquote key={i} className="my-4 border-l-4 border-[#2E5D4F] pl-4 py-1 text-sm leading-relaxed italic opacity-90">
                {renderInline(b.text, `q-${i}`)}
              </blockquote>
            );
          case 'ul':
            return (
              <ul key={i} className="my-3 space-y-1.5 list-disc pl-5 text-sm leading-relaxed marker:text-[#2E5D4F]">
                {b.items.map((it, j) => <li key={j}>{renderInline(it, `ul-${i}-${j}`)}</li>)}
              </ul>
            );
          case 'ol':
            return (
              <ol key={i} className="my-3 space-y-1.5 list-decimal pl-5 text-sm leading-relaxed marker:text-[#2E5D4F] marker:font-semibold">
                {b.items.map((it, j) => <li key={j}>{renderInline(it, `ol-${i}-${j}`)}</li>)}
              </ol>
            );
          default:
            return <p key={i} className="my-3 text-sm leading-relaxed text-current">{renderInline(b.text, `p-${i}`)}</p>;
        }
      })}
    </div>
  );
}
