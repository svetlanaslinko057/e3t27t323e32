/**
 * PublicContractView — unauthenticated route /c/view/:token
 *
 * The investor opens a one-time link and can:
 *   1. Read the contract body.
 *   2. Download the rendered PDF.
 *   3. Sign electronically (must confirm e-mail match).
 *
 * No auth required. Backend enforces identity via e-mail match
 * against the contract's recipient.
 */
import { useEffect, useState } from "react";
import { formatUSD, usdFromUah } from "@/lib/lumenApi";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, FileText, Download, AlertTriangle, Loader2, ShieldCheck } from "lucide-react";
import SeoHead from "@/components/SeoHead";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";

export default function PublicContractView() {
  const { token } = useParams();
  const [contract, setContract] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [signerEmail, setSignerEmail] = useState("");
  const [signerName, setSignerName] = useState("");
  const [signerTaxId, setSignerTaxId] = useState("");
  const [agree, setAgree] = useState(false);
  const [signing, setSigning] = useState(false);
  const [signResult, setSignResult] = useState(null);
  const [signError, setSignError] = useState(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const r = await axios.get(`${BACKEND}/api/contracts/view/${encodeURIComponent(token)}`);
        if (mounted) setContract(r.data);
      } catch (e) {
        if (!mounted) return;
        const code = e?.response?.status;
        const detail = e?.response?.data?.detail || "Помилка завантаження";
        if (code === 404) setError({ kind: "not_found", detail: "Посилання не знайдено або вже неактивне" });
        else if (code === 410) setError({ kind: "expired", detail });
        else setError({ kind: "unknown", detail });
      } finally {
        mounted && setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [token]);

  const submitSign = async () => {
    setSigning(true);
    setSignError(null);
    try {
      const r = await axios.post(`${BACKEND}/api/contracts/view/${encodeURIComponent(token)}/sign`, {
        agree: true,
        signer_email: signerEmail.trim(),
        signer_name: signerName.trim() || null,
        signer_tax_id: signerTaxId.trim() || null,
      });
      setSignResult(r.data);
      // refresh contract view
      try {
        const fresh = await axios.get(`${BACKEND}/api/contracts/view/${encodeURIComponent(token)}`);
        setContract(fresh.data);
      } catch (_) {}
    } catch (e) {
      setSignError(e?.response?.data?.detail || "Не вдалося підписати");
    } finally {
      setSigning(false);
    }
  };

  const downloadPdf = () => {
    window.location.href = `${BACKEND}/api/contracts/view/${encodeURIComponent(token)}/download`;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <SeoHead title="Завантаження договору" noIndex path={`/c/view/${token}`} />
        <div className="flex items-center gap-2 text-slate-600">
          <Loader2 className="h-5 w-5 animate-spin" />
          Завантаження…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
        <SeoHead title="Договір недоступний" noIndex path={`/c/view/${token}`} />
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-rose-700">
              <AlertTriangle className="h-5 w-5" />
              Договір недоступний
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-slate-700">{error.detail}</p>
            <p className="mt-3 text-sm text-slate-500">
              Зверніться до менеджера, який надіслав вам посилання, щоб отримати нове.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isSigned = contract?.status === "signed";
  const canSign = ["sent", "viewed", "generated"].includes(contract?.status);

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4">
      <SeoHead title="Договір" noIndex path={`/c/view/${token}`} />
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2 text-slate-500 text-sm">
                  <FileText className="h-4 w-4" />
                  Договір № {contract.number}
                </div>
                <h1 className="text-2xl font-bold text-slate-900 mt-1">{contract.title}</h1>
                <p className="text-slate-600 mt-1">
                  {contract.asset_title} · {contract.investor_name}
                </p>
              </div>
              <div>
                <Button variant="outline" onClick={downloadPdf} data-testid="download-pdf-btn">
                  <Download className="h-4 w-4 mr-2" />
                  Завантажити PDF
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-slate-600">
              <span className="font-medium">Статус:</span>{" "}
              <span className={isSigned ? "text-emerald-700 font-medium" : "text-amber-700 font-medium"}>
                {contract.status_label}
              </span>
              {contract.amount ? (
                <span className="ml-4">
                  <span className="font-medium">Сума:</span> {formatUSD(usdFromUah(contract.amount))}
                </span>
              ) : null}
            </div>
          </CardContent>
        </Card>

        {/* Body */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Текст договору</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm text-slate-800 leading-relaxed font-sans">
              {contract.body_text}
            </pre>
          </CardContent>
        </Card>

        {/* Signature panel */}
        {isSigned ? (
          <Card className="border-emerald-200 bg-emerald-50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-emerald-800">
                <CheckCircle2 className="h-5 w-5" />
                Договір підписано
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-emerald-900 space-y-1">
              <div>
                <span className="font-medium">Підписано:</span>{" "}
                {new Date(contract.signed_at).toLocaleString("uk-UA")}
              </div>
              {contract.signature?.ip && (
                <div>
                  <span className="font-medium">IP:</span> {contract.signature.ip}
                </div>
              )}
              <Alert className="mt-4 border-emerald-300 bg-white">
                <ShieldCheck className="h-4 w-4 text-emerald-700" />
                <AlertDescription className="text-slate-700">
                  Електронне прийняття зафіксовано в реєстрі підписів LUMEN. Очікуйте
                  на повідомлення з реквізитами для оплати.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>
        ) : canSign ? (
          <Card>
            <CardHeader>
              <CardTitle>Електронне підписання</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert>
                <AlertDescription>
                  Введіть e-mail, на який було надіслано це посилання. Після підписання
                  ми зафіксуємо IP-адресу, час і параметри пристрою як юридичний доказ.
                </AlertDescription>
              </Alert>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="signer_email">E-mail отримувача *</Label>
                  <Input
                    id="signer_email"
                    data-testid="signer-email-input"
                    type="email"
                    value={signerEmail}
                    onChange={(e) => setSignerEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                  />
                </div>
                <div>
                  <Label htmlFor="signer_name">Ваше ПІБ</Label>
                  <Input
                    id="signer_name"
                    data-testid="signer-name-input"
                    value={signerName}
                    onChange={(e) => setSignerName(e.target.value)}
                    placeholder="Іваненко Іван Іванович"
                  />
                </div>
                <div className="md:col-span-2">
                  <Label htmlFor="signer_tax_id">РНОКПП (необов'язково)</Label>
                  <Input
                    id="signer_tax_id"
                    data-testid="signer-taxid-input"
                    value={signerTaxId}
                    onChange={(e) => setSignerTaxId(e.target.value)}
                    placeholder="1234567890"
                  />
                </div>
              </div>
              <div className="flex items-start gap-3 pt-2">
                <Checkbox
                  id="agree"
                  data-testid="agree-checkbox"
                  checked={agree}
                  onCheckedChange={(v) => setAgree(!!v)}
                />
                <label htmlFor="agree" className="text-sm text-slate-700 leading-tight">
                  Я ознайомлений з умовами договору, погоджуюсь з ними і підтверджую
                  свою згоду на електронне підписання документа.
                </label>
              </div>
              {signError && (
                <Alert variant="destructive">
                  <AlertDescription>{signError}</AlertDescription>
                </Alert>
              )}
              <Button
                onClick={submitSign}
                disabled={!agree || !signerEmail.trim() || signing}
                data-testid="sign-btn"
                className="w-full md:w-auto"
              >
                {signing ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Підписуємо…
                  </>
                ) : (
                  <>
                    <ShieldCheck className="h-4 w-4 mr-2" />
                    Підписати договір
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="py-6 text-amber-900">
              Підписання цього договору наразі недоступне (статус: {contract.status_label}).
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
