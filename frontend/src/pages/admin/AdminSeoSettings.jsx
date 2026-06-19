/**
 * AdminSeoSettings — admin page for the SEO control surface.
 *
 * Wires GET/PATCH /api/admin/seo/settings + POST /api/admin/seo/cache/invalidate.
 * Lets admins edit:
 *   - Public origin (canonical base URL)
 *   - Title template (must contain %s)
 *   - Default page title / description / OG image
 *   - JSON-LD Organization (name, URL, logo, sameAs[])
 *   - Twitter handle
 *   - Enable blog in sitemap toggle
 *   - Extra robots.txt lines
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CheckCircle2, RefreshCw, Search, FileText, Globe, Loader2, ExternalLink } from "lucide-react";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
const client = axios.create({ baseURL: BACKEND, withCredentials: true });

export default function AdminSeoSettings() {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await client.get("/api/admin/seo/settings");
      setSettings(r.data);
      setDraft(r.data);
      setPreviewUrl(`${BACKEND}/api/seo/sitemap.xml`);
    } catch (e) {
      setError(e?.response?.data?.detail || "Помилка завантаження");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));

  const save = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const diff = {};
      for (const k of Object.keys(draft || {})) {
        if (JSON.stringify(draft[k]) !== JSON.stringify(settings?.[k])) {
          diff[k] = draft[k];
        }
      }
      if (!Object.keys(diff).length) {
        setSuccess("Немає змін для збереження");
        setSaving(false);
        return;
      }
      const r = await client.patch("/api/admin/seo/settings", diff);
      setSettings(r.data);
      setDraft(r.data);
      setSuccess(`Збережено (версія v${r.data.version})`);
    } catch (e) {
      setError(e?.response?.data?.detail || "Помилка збереження");
    } finally {
      setSaving(false);
    }
  };

  const invalidateCache = async () => {
    try {
      await client.post("/api/admin/seo/cache/invalidate");
      setSuccess("Кеш sitemap скинуто — наступний запит згенерує свіжу мапу");
    } catch (e) {
      setError(e?.response?.data?.detail || "Не вдалося скинути кеш");
    }
  };

  if (loading)
    return (
      <div className="flex items-center gap-2 text-slate-600 p-6">
        <Loader2 className="h-5 w-5 animate-spin" />
        Завантаження…
      </div>
    );

  if (!draft) return null;

  return (
    <div className="space-y-6 p-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Search className="h-6 w-6 text-primary" />
          SEO & Discoverability
        </h1>
        <p className="text-slate-600 mt-1">
          Контролює sitemap, robots, runtime-конфіг для SeoHead та JSON-LD Organization.
          Зміни одразу попадають у sitemap (через ручний скид кешу) та у наступне завантаження SPA.
        </p>
        <div className="mt-2 text-xs text-slate-500">
          Версія: <span className="font-mono">v{settings?.version}</span>
          {settings?.updated_at && (
            <>
              {" · "}
              Останнє оновлення: {new Date(settings.updated_at).toLocaleString("uk-UA")}
            </>
          )}
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {success && (
        <Alert className="border-emerald-200 bg-emerald-50">
          <CheckCircle2 className="h-4 w-4 text-emerald-700" />
          <AlertDescription className="text-emerald-900">{success}</AlertDescription>
        </Alert>
      )}

      {/* Section 1: Identity & origin */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Globe className="h-4 w-4" />
            Канонічний домен та title
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="origin">Origin (без слешу в кінці)</Label>
            <Input
              id="origin"
              data-testid="seo-origin-input"
              value={draft.origin || ""}
              onChange={(e) => set("origin", e.target.value)}
              placeholder="https://lumen.com.ua"
            />
            <p className="text-xs text-slate-500 mt-1">
              Використовується для всіх canonical-посилань, sitemap і OG-тегів. Якщо порожньо — береться з заголовка Host.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="title_template">Шаблон title (мусить містити %s)</Label>
              <Input
                id="title_template"
                data-testid="seo-tpl-input"
                value={draft.title_template || ""}
                onChange={(e) => set("title_template", e.target.value)}
                placeholder="%s · LUMEN"
              />
            </div>
            <div>
              <Label htmlFor="default_locale">Default locale</Label>
              <Input
                id="default_locale"
                data-testid="seo-locale-input"
                value={draft.default_locale || ""}
                onChange={(e) => set("default_locale", e.target.value)}
                placeholder="uk_UA"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section 2: defaults */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4" />
            Дефолтні мета-теги
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="default_title">Default title</Label>
            <Input
              id="default_title"
              data-testid="seo-deftitle-input"
              value={draft.default_title || ""}
              onChange={(e) => set("default_title", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="default_description">Default description</Label>
            <Textarea
              id="default_description"
              data-testid="seo-defdesc-input"
              rows={3}
              value={draft.default_description || ""}
              onChange={(e) => set("default_description", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="default_og_image">Default OG image URL</Label>
            <Input
              id="default_og_image"
              data-testid="seo-ogimg-input"
              value={draft.default_og_image || ""}
              onChange={(e) => set("default_og_image", e.target.value)}
              placeholder="https://lumen.com.ua/og-default.jpg"
            />
          </div>
          <div>
            <Label htmlFor="twitter_handle">Twitter handle</Label>
            <Input
              id="twitter_handle"
              data-testid="seo-twitter-input"
              value={draft.twitter_handle || ""}
              onChange={(e) => set("twitter_handle", e.target.value)}
              placeholder="@lumen_invest"
            />
          </div>
        </CardContent>
      </Card>

      {/* Section 3: JSON-LD */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">JSON-LD Organization</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="jsonld_org_name">Name</Label>
              <Input
                id="jsonld_org_name"
                value={draft.jsonld_org_name || ""}
                onChange={(e) => set("jsonld_org_name", e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="jsonld_org_url">URL</Label>
              <Input
                id="jsonld_org_url"
                value={draft.jsonld_org_url || ""}
                onChange={(e) => set("jsonld_org_url", e.target.value)}
              />
            </div>
          </div>
          <div>
            <Label htmlFor="jsonld_org_logo">Logo URL</Label>
            <Input
              id="jsonld_org_logo"
              value={draft.jsonld_org_logo || ""}
              onChange={(e) => set("jsonld_org_logo", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="jsonld_org_sameAs">sameAs (один URL на рядок)</Label>
            <Textarea
              id="jsonld_org_sameAs"
              rows={3}
              value={(draft.jsonld_org_sameAs || []).join("\n")}
              onChange={(e) =>
                set(
                  "jsonld_org_sameAs",
                  e.target.value
                    .split("\n")
                    .map((s) => s.trim())
                    .filter(Boolean)
                )
              }
              placeholder="https://t.me/lumen_invest&#10;https://www.linkedin.com/company/lumen-invest"
            />
          </div>
        </CardContent>
      </Card>

      {/* Section 4: Sitemap & robots */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sitemap і robots</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Switch
              id="enable_blog"
              data-testid="seo-blog-switch"
              checked={!!draft.enable_blog_in_sitemap}
              onCheckedChange={(v) => set("enable_blog_in_sitemap", !!v)}
            />
            <Label htmlFor="enable_blog">Включати блог-пости у sitemap</Label>
          </div>
          <div>
            <Label htmlFor="robots_extras">Додаткові рядки до robots.txt</Label>
            <Textarea
              id="robots_extras"
              rows={3}
              value={draft.robots_extras || ""}
              onChange={(e) => set("robots_extras", e.target.value)}
              placeholder="Disallow: /draft/&#10;Crawl-delay: 10"
            />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="outline" size="sm" onClick={invalidateCache} data-testid="seo-flush-btn">
              <RefreshCw className="h-4 w-4 mr-2" />
              Скинути кеш sitemap
            </Button>
            <a
              href={previewUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              Переглянути sitemap.xml
            </a>
            <a
              href={`${BACKEND}/api/seo/robots.txt`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              Переглянути robots.txt
            </a>
            <a
              href={`${BACKEND}/api/seo/runtime-config`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              Переглянути runtime-config
            </a>
          </div>
        </CardContent>
      </Card>

      <div className="sticky bottom-4 bg-white border border-slate-200 shadow-lg rounded-lg p-4 flex items-center justify-end gap-3">
        <Button variant="outline" onClick={load} disabled={saving}>
          Відмінити
        </Button>
        <Button onClick={save} disabled={saving} data-testid="seo-save-btn">
          {saving ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Зберігаємо…
            </>
          ) : (
            "Зберегти"
          )}
        </Button>
      </div>
    </div>
  );
}
