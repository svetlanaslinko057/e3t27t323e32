/**
 * SeoHead — declaratively manages <title>, <meta>, <link rel=canonical>,
 * Open Graph, Twitter Card, and JSON-LD Organization schema for every page.
 *
 * Backed by GET /api/seo/runtime-config — the React shell fetches the
 * runtime config ONCE at mount and merges per-page overrides on top.
 *
 * Usage on any page:
 *   <SeoHead title="Marketplace" description="All published assets..."
 *            ogImage="https://..." path="/marketplace" />
 *
 * Notes:
 *   - We avoid pulling in react-helmet to keep the bundle slim. Manual
 *     DOM ops are scoped to known managed nodes (data-seo="...") so the
 *     component cleanly removes its own tags on unmount.
 *   - JSON-LD is emitted only on the LANDING page (path="/") to avoid
 *     duplicate Organization schemas across the site.
 */
import { useEffect, useState } from "react";
import axios from "axios";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
let _cached = null;
let _inflight = null;

async function loadSeoConfig() {
  if (_cached) return _cached;
  if (_inflight) return _inflight;
  _inflight = axios
    .get(`${BACKEND}/api/seo/runtime-config`, { withCredentials: false })
    .then((r) => {
      _cached = r.data || {};
      return _cached;
    })
    .catch(() => ({}))
    .finally(() => {
      _inflight = null;
    });
  return _inflight;
}

function _setMeta(name, content, attr = "name") {
  if (!content) return null;
  let el = document.head.querySelector(`meta[${attr}="${name}"][data-seo="head"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, name);
    el.setAttribute("data-seo", "head");
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
  return el;
}

function _setLink(rel, href) {
  if (!href) return null;
  let el = document.head.querySelector(`link[rel="${rel}"][data-seo="head"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    el.setAttribute("data-seo", "head");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
  return el;
}

function _setJsonLd(json) {
  document.head
    .querySelectorAll('script[type="application/ld+json"][data-seo="head"]')
    .forEach((n) => n.remove());
  if (!json) return;
  const s = document.createElement("script");
  s.type = "application/ld+json";
  s.setAttribute("data-seo", "head");
  s.textContent = JSON.stringify(json);
  document.head.appendChild(s);
}

export default function SeoHead({
  title,
  description,
  ogImage,
  path,
  noIndex = false,
  emitOrganization = false,
}) {
  const [cfg, setCfg] = useState(_cached || {});

  useEffect(() => {
    let mounted = true;
    if (!_cached) {
      loadSeoConfig().then((c) => mounted && setCfg(c));
    }
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const origin = cfg.origin || (typeof window !== "undefined" ? window.location.origin : "");
    const tpl = cfg.title_template || "%s · LUMEN";
    const dflt = cfg.default_title || "LUMEN — Реальні активи. Прозорі інвестиції.";
    const finalTitle = title ? tpl.replace("%s", title) : dflt;
    document.title = finalTitle;

    const desc = description || cfg.default_description || "";
    _setMeta("description", desc);

    const og = ogImage || cfg.default_og_image || "";
    _setMeta("og:title", finalTitle, "property");
    _setMeta("og:description", desc, "property");
    _setMeta("og:type", "website", "property");
    _setMeta("og:locale", cfg.default_locale || "uk_UA", "property");
    if (og) _setMeta("og:image", og, "property");

    _setMeta("twitter:card", og ? "summary_large_image" : "summary");
    if (cfg.twitter_handle) _setMeta("twitter:site", cfg.twitter_handle);
    if (og) _setMeta("twitter:image", og);

    if (path && origin) {
      const canonical = `${origin.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
      _setLink("canonical", canonical);
      _setMeta("og:url", canonical, "property");
    }

    if (noIndex) {
      _setMeta("robots", "noindex, nofollow");
    } else {
      _setMeta("robots", "index, follow");
    }

    if (emitOrganization && cfg.jsonld_org && cfg.jsonld_org.name) {
      const org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        name: cfg.jsonld_org.name,
        url: cfg.jsonld_org.url || origin,
        logo: cfg.jsonld_org.logo || undefined,
        sameAs: cfg.jsonld_org.sameAs && cfg.jsonld_org.sameAs.length ? cfg.jsonld_org.sameAs : undefined,
      };
      _setJsonLd(org);
    }

    return () => {
      // We intentionally LEAVE the tags in place; SPA navigations will overwrite
      // by selector. On true unmount of the *whole* SPA (rare), removing them
      // would create a flash.
    };
  }, [title, description, ogImage, path, noIndex, emitOrganization, cfg]);

  return null;
}
