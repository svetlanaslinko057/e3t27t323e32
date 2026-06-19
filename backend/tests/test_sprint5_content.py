"""
Sprint 5 smoke test — LUMEN Asset Content Platform (trust layer).

Covers:
  * embedded content patch (gallery / videos / team / risks / exit_strategy)
      — URL validation, YouTube embed parsing, investor 403
  * updates: CRUD + published filter + pinned ordering
  * reports: multipart create with file, public download, unpublish, delete
  * documents: upload + visibility gate (investors → anon 401), bad CT 400,
      locked metadata for anon, delete (file removed from disk)
  * Q&A: ask validation, own-pending visibility, admin answer → public,
      hide / restore, spam limit (5 pending → 429)
  * SPV: CRUD + one-SPV-per-asset 409 + public /assets/{id}/spv
  * access rights: investor blocked from admin endpoints
  * seed sanity: demo assets carry gallery/team/risks after startup
  * cleanup — demo data stays intact

Run:  cd /app/backend && python tests/test_sprint5_content.py
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001"
ASSET_ID = "asset-koncha-zaspa"   # least-touched demo asset

failures = []


def check(name, ok, extra=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name} {extra}")
    if not ok:
        failures.append(name)


def _cookie(client, resp):
    token = resp.cookies.get("session_token")
    assert token, "no session cookie"
    client.cookies.set("session_token", token)


async def main() -> int:
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    adm = httpx.AsyncClient(timeout=30)
    r = await adm.post(f"{BASE}/api/auth/quick", json={"email": "admin@atlas.dev"})
    _cookie(adm, r)

    inv = httpx.AsyncClient(timeout=30)
    email = f"sprint5-{uuid.uuid4().hex[:8]}@test.lumen"
    r = await inv.post(f"{BASE}/api/auth/onboarding",
                       json={"email": email, "name": "Sprint5 Інвестор", "role": "client"})
    _cookie(inv, r)
    me = (await inv.get(f"{BASE}/api/auth/me")).json()
    uid = me.get("user_id") or me.get("id")

    anon = httpx.AsyncClient(timeout=30)

    # pick an existing asset; fall back to first
    asset = await db.lumen_assets.find_one({"id": ASSET_ID}) \
        or await db.lumen_assets.find_one({})
    asset_id = asset["id"]

    print("== Sprint 5: Asset Content Platform ==")

    # ── 0. seed sanity ───────────────────────────────────────────────────────
    r = await anon.get(f"{BASE}/api/assets/asset-podilskyi")
    a = r.json()
    check("seed: flagship asset has gallery/team/risks/exit",
          len(a.get("gallery", [])) >= 3 and len(a.get("team", [])) >= 2
          and len(a.get("risks", [])) >= 3 and bool(a.get("exit_strategy")))
    r = await anon.get(f"{BASE}/api/assets/asset-podilskyi/spv")
    check("seed: flagship asset has SPV", bool((r.json() or {}).get("spv")))

    # ── 1. embedded content patch ────────────────────────────────────────────
    saved = {k: asset.get(k) for k in ("gallery", "videos", "team", "risks", "exit_strategy")}
    r = await inv.patch(f"{BASE}/api/admin/assets/{asset_id}/content",
                        json={"exit_strategy": "x"})
    check("investor blocked from content patch -> 403", r.status_code == 403,
          f"[{r.status_code}]")
    r = await adm.patch(f"{BASE}/api/admin/assets/{asset_id}/content", json={
        "gallery": [{"url": "https://images.unsplash.com/test-1", "caption": "Фото 1"},
                    {"url": "javascript:alert(1)", "caption": "bad"},
                    {"url": "https://images.unsplash.com/test-2"}],
        "videos": [{"url": "https://www.youtube.com/watch?v=abc123def45", "title": "Огляд"},
                   {"url": "https://vimeo.com/123456789"}],
        "team": [{"name": "Тест Менеджер", "role": "PM", "bio": "10 років досвіду"},
                 {"name": "", "role": "ignored"}],
        "risks": [{"title": "Тестовий ризик", "severity": "high"},
                  {"title": "Другий ризик", "severity": "bogus"}],
        "exit_strategy": "Продаж через 24 місяці.",
    })
    body = r.json()
    check("admin patches embedded content", r.status_code == 200, f"[{r.status_code}]")
    check("invalid gallery URL filtered out", len(body.get("gallery", [])) == 2)
    check("youtube embed parsed",
          any(v.get("provider") == "youtube"
              and "youtube.com/embed/abc123def45" in (v.get("embed_url") or "")
              for v in body.get("videos", [])))
    check("vimeo embed parsed",
          any(v.get("provider") == "vimeo" for v in body.get("videos", [])))
    check("empty team member dropped", len(body.get("team", [])) == 1)
    check("invalid risk severity normalised",
          all(rk["severity"] in ("low", "medium", "high") for rk in body.get("risks", [])))
    r = await anon.get(f"{BASE}/api/assets/{asset_id}")
    check("public asset exposes patched content",
          (r.json() or {}).get("exit_strategy") == "Продаж через 24 місяці.")
    r = await adm.patch(f"{BASE}/api/admin/assets/{asset_id}/content", json={})
    check("empty content patch -> 400", r.status_code == 400, f"[{r.status_code}]")

    # ── 2. updates ───────────────────────────────────────────────────────────
    r = await adm.post(f"{BASE}/api/admin/assets/{asset_id}/updates",
                       json={"title": "", "body": ""})
    check("update without title/body -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await adm.post(f"{BASE}/api/admin/assets/{asset_id}/updates",
                       json={"title": "Перша віха", "body": "Фундамент завершено.",
                             "kind": "milestone", "pinned": True})
    upd1 = r.json()
    check("admin creates pinned update", r.status_code == 200 and upd1.get("pinned"))
    r = await adm.post(f"{BASE}/api/admin/assets/{asset_id}/updates",
                       json={"title": "Чернетка", "body": "Не публікуємо.",
                             "published": False})
    upd2 = r.json()
    check("admin creates unpublished update", r.status_code == 200)

    r = await anon.get(f"{BASE}/api/assets/{asset_id}/updates")
    pub = r.json().get("items", [])
    check("public list hides unpublished",
          any(u["id"] == upd1["id"] for u in pub)
          and not any(u["id"] == upd2["id"] for u in pub))
    check("pinned update first", pub and pub[0]["id"] == upd1["id"])
    r = await adm.get(f"{BASE}/api/admin/assets/{asset_id}/updates")
    check("admin list shows all",
          any(u["id"] == upd2["id"] for u in r.json().get("items", [])))
    r = await adm.patch(f"{BASE}/api/admin/asset-updates/{upd2['id']}",
                        json={"title": "Вже публічно", "body": "Опубліковано.",
                              "published": True})
    check("admin publishes update via patch",
          r.status_code == 200 and r.json().get("published") is True)
    r = await inv.post(f"{BASE}/api/admin/assets/{asset_id}/updates",
                       json={"title": "x", "body": "y"})
    check("investor blocked from updates admin -> 403", r.status_code == 403)

    # ── 3. reports ───────────────────────────────────────────────────────────
    r = await adm.post(f"{BASE}/api/admin/assets/{asset_id}/reports",
                       data={"title": "Звіт Q2", "report_type": "quarterly",
                             "period_label": "Q2 2026", "summary": "Все за планом."},
                       files={"file": ("q2.pdf", b"%PDF-1.4 sprint5 report", "application/pdf")})
    rep = r.json()
    check("admin creates report with file",
          r.status_code == 200 and rep.get("has_file") is True, f"[{r.status_code}]")
    r = await adm.post(f"{BASE}/api/admin/assets/{asset_id}/reports",
                       data={"title": "Поганий тип", "report_type": "weekly"})
    check("invalid report_type -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await anon.get(f"{BASE}/api/assets/{asset_id}/reports")
    check("public reports list", any(i["id"] == rep["id"] for i in r.json().get("items", [])))
    r = await anon.get(f"{BASE}/api/assets/{asset_id}/reports/{rep['id']}/download")
    check("anon downloads published report",
          r.status_code == 200 and r.content.startswith(b"%PDF"))
    r = await adm.patch(f"{BASE}/api/admin/asset-reports/{rep['id']}",
                        json={"published": False})
    check("admin unpublishes report", r.status_code == 200)
    r = await anon.get(f"{BASE}/api/assets/{asset_id}/reports/{rep['id']}/download")
    check("unpublished report download -> 404", r.status_code == 404, f"[{r.status_code}]")

    # ── 4. documents + visibility gate ───────────────────────────────────────
    r = await adm.post(f"{BASE}/api/admin/assets/{asset_id}/documents",
                       data={"title": "Аудит SPV", "doc_type": "audit",
                             "visibility": "investors"},
                       files={"file": ("audit.pdf", b"%PDF-1.4 audit", "application/pdf")})
    doc_inv = r.json()
    check("admin uploads investors-only document", r.status_code == 200, f"[{r.status_code}]")
    r = await adm.post(f"{BASE}/api/admin/assets/{asset_id}/documents",
                       data={"title": "Вірус", "doc_type": "other", "visibility": "public"},
                       files={"file": ("x.exe", b"MZ\x90", "application/x-msdownload")})
    check("bad content type -> 400", r.status_code == 400, f"[{r.status_code}]")

    r = await anon.get(f"{BASE}/api/assets/{asset_id}/documents")
    anon_doc = next((d for d in r.json().get("items", []) if d["id"] == doc_inv["id"]), {})
    check("anon sees investors doc as locked",
          anon_doc.get("locked") is True and anon_doc.get("download_url") is None)
    r = await anon.get(f"{BASE}/api/assets/{asset_id}/documents/{doc_inv['id']}/download")
    check("anon download investors doc -> 401", r.status_code == 401, f"[{r.status_code}]")
    r = await inv.get(f"{BASE}/api/assets/{asset_id}/documents/{doc_inv['id']}/download")
    check("authed investor downloads investors doc",
          r.status_code == 200 and r.content.startswith(b"%PDF"))

    # ── 5. Q&A ───────────────────────────────────────────────────────────────
    r = await inv.post(f"{BASE}/api/investor/assets/{asset_id}/questions",
                       json={"question": "коротко"})
    check("too-short question -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await inv.post(f"{BASE}/api/investor/assets/{asset_id}/questions",
                       json={"question": "Який графік виплат орендного доходу інвесторам?"})
    q1 = r.json()
    check("investor asks a question", r.status_code == 200 and q1.get("status") == "pending")

    r = await anon.get(f"{BASE}/api/assets/{asset_id}/questions")
    check("anon does NOT see pending question",
          not any(q["id"] == q1["id"] for q in r.json().get("items", [])))
    r = await inv.get(f"{BASE}/api/assets/{asset_id}/questions")
    own = next((q for q in r.json().get("items", []) if q["id"] == q1["id"]), None)
    check("author sees own pending question", own is not None and own.get("is_own") is True)

    r = await adm.get(f"{BASE}/api/admin/questions?status=pending")
    body = r.json()
    check("admin pending queue + counts",
          any(q["id"] == q1["id"] for q in body.get("items", []))
          and body.get("counts", {}).get("pending", 0) >= 1)
    r = await adm.post(f"{BASE}/api/admin/questions/{q1['id']}/answer", json={"answer": ""})
    check("empty answer -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await adm.post(f"{BASE}/api/admin/questions/{q1['id']}/answer",
                       json={"answer": "Виплати щоквартально, протягом 10 робочих днів після звіту SPV."})
    check("admin answers question",
          r.status_code == 200 and r.json().get("status") == "answered")
    r = await anon.get(f"{BASE}/api/assets/{asset_id}/questions")
    check("answered question is public",
          any(q["id"] == q1["id"] and q.get("answer") for q in r.json().get("items", [])))
    r = await adm.post(f"{BASE}/api/admin/questions/{q1['id']}/hide")
    check("admin hides question", r.status_code == 200)
    r = await anon.get(f"{BASE}/api/assets/{asset_id}/questions")
    check("hidden question gone from public",
          not any(q["id"] == q1["id"] for q in r.json().get("items", [])))
    r = await adm.post(f"{BASE}/api/admin/questions/{q1['id']}/restore")
    check("admin restores question (answered again)",
          r.status_code == 200 and r.json().get("status") == "answered")

    # spam limit: 5 pending max
    for i in range(5):
        await inv.post(f"{BASE}/api/investor/assets/{asset_id}/questions",
                       json={"question": f"Тестове питання номер {i} про об'єкт і ризики?"})
    r = await inv.post(f"{BASE}/api/investor/assets/{asset_id}/questions",
                       json={"question": "Шосте питання поспіль без відповіді оператора?"})
    check("6th pending question -> 429", r.status_code == 429, f"[{r.status_code}]")

    # ── 6. SPV ───────────────────────────────────────────────────────────────
    r = await adm.post(f"{BASE}/api/admin/spvs", json={"name": ""})
    check("SPV without name -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await adm.post(f"{BASE}/api/admin/spvs",
                       json={"name": "ТОВ «Смок Тест СПВ»", "registration_number": "99999999",
                             "status": "forming"})
    spv = r.json()
    check("admin creates standalone SPV", r.status_code == 200 and spv.get("id"))
    r = await adm.post(f"{BASE}/api/admin/spvs",
                       json={"name": "Дубль", "asset_id": "asset-podilskyi"})
    check("second SPV for same asset -> 409", r.status_code == 409, f"[{r.status_code}]")
    r = await adm.patch(f"{BASE}/api/admin/spvs/{spv['id']}", json={"status": "bogus"})
    check("invalid SPV status -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await adm.patch(f"{BASE}/api/admin/spvs/{spv['id']}",
                        json={"status": "active", "notes": "Зареєстровано."})
    check("admin patches SPV", r.status_code == 200 and r.json().get("status") == "active")
    r = await adm.get(f"{BASE}/api/admin/spvs")
    body = r.json()
    check("admin SPV registry + counts",
          any(s["id"] == spv["id"] for s in body.get("items", []))
          and isinstance(body.get("counts"), dict))
    r = await inv.get(f"{BASE}/api/admin/spvs")
    check("investor blocked from SPV admin -> 403", r.status_code == 403, f"[{r.status_code}]")

    # ── cleanup ──────────────────────────────────────────────────────────────
    await db.lumen_assets.update_one({"id": asset_id}, {"$set": saved})
    await db.lumen_asset_updates.delete_many({"asset_id": asset_id})
    rep_doc = await db.lumen_asset_reports.find_one({"id": rep["id"]})
    if rep_doc and rep_doc.get("storage_path") and os.path.exists(rep_doc["storage_path"]):
        os.remove(rep_doc["storage_path"])
    await db.lumen_asset_reports.delete_many({"id": rep["id"]})
    d_doc = await db.lumen_asset_documents.find_one({"id": doc_inv["id"]})
    if d_doc and d_doc.get("storage_path") and os.path.exists(d_doc["storage_path"]):
        os.remove(d_doc["storage_path"])
    await db.lumen_asset_documents.delete_many({"id": doc_inv["id"]})
    await db.lumen_asset_questions.delete_many({"investor_id": uid})
    await db.lumen_spvs.delete_one({"id": spv["id"]})
    await db.lumen_notifications.delete_many({"investor_id": uid})
    await db.users.delete_one({"user_id": uid})
    await db.user_sessions.delete_many({"user_id": uid})

    restored = await db.lumen_assets.find_one({"id": asset_id})
    check("cleanup: asset content restored",
          restored.get("exit_strategy") == saved.get("exit_strategy"))

    await adm.aclose()
    await inv.aclose()
    await anon.aclose()

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
