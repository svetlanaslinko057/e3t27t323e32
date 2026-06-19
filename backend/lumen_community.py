"""
LUMEN Phase C — Ownership Community OS.

The strategic pivot after Phase B: LUMEN can buy / account / pay out / resell,
but the real deficit is a REASON TO COME BACK between purchase and sale.
Community OS closes that — but it is NOT a forum / social network / Telegram.
It is community built AROUND a concrete asset, gated by real ownership (units).

Blocks (one designed layer):

  C1 Asset Feed        — per-asset feed: announcements + questions + discussions
  C2 Ownership Lounge  — units-gated space (have units → see lounge discussions)
  C3 Questions 2.0     — question → operator answer → investor discussion (comments)
  C4 Voting            — polls where WEIGHT = units owned (advisory, not legal)
  C5 Asset Sentiment   — holder mood pulse (positive/neutral/negative), unit-weighted
  C6 Reputation        — per-asset reputation (activity / participation), not global karma
  C7 Announcements     — operator publishes (tenant / repair / report / payout) → notifies holders

Source of truth for access = lumen_ownerships (units per investor per asset).
All numbers derived from real data — no mocks.

Collections:
  lumen_community_posts      discussion / question / announcement threads
  lumen_community_comments   comments under a post
  lumen_community_polls      unit-weighted polls (C4)
  lumen_community_ballots    one ballot per (poll, voter), stores units_weight snapshot
  lumen_community_sentiment  one mood pulse per (asset, holder)  (C5)
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from lumen_api import db, get_current_user, require_admin, _now, _iso

logger = logging.getLogger("lumen.community")

router = APIRouter(prefix="/api", tags=["lumen-community"])

POST_KINDS = {"discussion", "question", "announcement"}
REACTIONS = {"like", "insightful", "concern"}
REACTION_LABELS = {"like": "Підтримую", "insightful": "Корисно", "concern": "Занепокоєння"}
MOODS = {"positive", "neutral", "negative"}
MOOD_LABELS = {"positive": "Задоволені", "neutral": "Нейтральні", "negative": "Занепокоєні"}

REP_TIERS = [
    (50, "leader", "Лідер спільноти"),
    (20, "active", "Активний учасник"),
    (5, "member", "Учасник"),
    (0, "observer", "Спостерігач"),
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _uid(user: dict) -> str:
    return user.get("user_id") or user.get("id")


def _clean(v: Any, n: int = 4000) -> str:
    return str(v or "").strip()[:n]


async def _optional_user(request: Request) -> Optional[dict]:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def _asset_or_404(asset_id: str) -> dict:
    a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    return a


async def _units_of(asset_id: str, uid: Optional[str]) -> float:
    if not uid:
        return 0.0
    own = await db.lumen_ownerships.find_one({"asset_id": asset_id, "investor_id": uid})
    if not own:
        return 0.0
    return float(own.get("units_int") or own.get("units") or 0)


def _is_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    roles = user.get("roles") or []
    return "admin" in roles


async def _holders_count(asset_id: str) -> int:
    n = 0
    async for o in db.lumen_ownerships.find({"asset_id": asset_id}):
        if float(o.get("units_int") or o.get("units") or 0) > 0:
            n += 1
    return n


# ──────────────────────────────────────────────────────────────────────────────
# C6 — Reputation (per-asset, derived from real activity)
# ──────────────────────────────────────────────────────────────────────────────

def _tier_for(score: float) -> tuple[str, str]:
    for threshold, key, label in REP_TIERS:
        if score >= threshold:
            return key, label
    return "observer", "Спостерігач"


async def _reputation(asset_id: str, uid: Optional[str]) -> dict:
    if not uid:
        return {"score": 0, "tier": "observer", "tier_label": "Спостерігач",
                "posts": 0, "comments": 0, "votes": 0, "reactions_received": 0}
    posts = await db.lumen_community_posts.count_documents(
        {"asset_id": asset_id, "author_id": uid, "status": "active"})
    comments = await db.lumen_community_comments.count_documents(
        {"asset_id": asset_id, "author_id": uid, "status": "active"})
    votes = await db.lumen_community_ballots.count_documents(
        {"asset_id": asset_id, "voter_id": uid})
    pulse = await db.lumen_community_sentiment.count_documents(
        {"asset_id": asset_id, "holder_id": uid})
    # reactions received across this author's posts
    reactions_received = 0
    async for p in db.lumen_community_posts.find(
            {"asset_id": asset_id, "author_id": uid}, {"reactions": 1}):
        for lst in (p.get("reactions") or {}).values():
            reactions_received += len(lst or [])
    score = posts * 5 + comments * 2 + votes * 3 + pulse * 1 + reactions_received * 1
    key, label = _tier_for(score)
    return {"score": score, "tier": key, "tier_label": label,
            "posts": posts, "comments": comments, "votes": votes,
            "reactions_received": reactions_received}


async def _rep_tier_map(asset_id: str, uids: list[str]) -> dict[str, dict]:
    """Lightweight tier lookup for a batch of authors (for feed chips)."""
    out: dict[str, dict] = {}
    for uid in set(filter(None, uids)):
        rep = await _reputation(asset_id, uid)
        out[uid] = {"tier": rep["tier"], "tier_label": rep["tier_label"], "score": rep["score"]}
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Serialization
# ──────────────────────────────────────────────────────────────────────────────

def _post_out(p: dict, *, uid: Optional[str], rep: Optional[dict] = None,
              with_counts: bool = True) -> dict:
    reactions = p.get("reactions") or {}
    counts = {k: len(reactions.get(k) or []) for k in REACTIONS}
    my = [k for k in REACTIONS if uid and uid in (reactions.get(k) or [])]
    return {
        "id": p["id"], "asset_id": p["asset_id"],
        "kind": p.get("kind", "discussion"),
        "title": p.get("title", ""), "body": p.get("body", ""),
        "author_id": p.get("author_id"),
        "author_name": "Оператор Lumen" if p.get("is_operator") else (p.get("author_name") or "Інвестор"),
        "is_operator": bool(p.get("is_operator")),
        "author_rep": rep,
        "visibility": p.get("visibility", "public"),
        "pinned": bool(p.get("pinned")),
        "answer": p.get("answer"),
        "answered_at": _iso(p.get("answered_at")),
        "comment_count": int(p.get("comment_count") or 0),
        "reaction_counts": counts,
        "my_reactions": my,
        "created_at": _iso(p.get("created_at")),
    }


def _comment_out(c: dict, *, uid: Optional[str]) -> dict:
    reactions = c.get("reactions") or {}
    return {
        "id": c["id"], "post_id": c["post_id"], "asset_id": c.get("asset_id"),
        "author_id": c.get("author_id"),
        "author_name": "Оператор Lumen" if c.get("is_operator") else (c.get("author_name") or "Інвестор"),
        "is_operator": bool(c.get("is_operator")),
        "body": c.get("body", ""),
        "like_count": len(reactions.get("like") or []),
        "my_like": bool(uid and uid in (reactions.get("like") or [])),
        "created_at": _iso(c.get("created_at")),
    }


# ──────────────────────────────────────────────────────────────────────────────
# C5 — Asset Sentiment (unit-weighted holder mood)
# ──────────────────────────────────────────────────────────────────────────────

async def _sentiment(asset_id: str) -> dict:
    weights = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
    voters = 0
    async for s in db.lumen_community_sentiment.find({"asset_id": asset_id}):
        mood = s.get("mood")
        if mood not in MOODS:
            continue
        w = float(s.get("units_weight") or 0) or 1.0
        weights[mood] += w
        voters += 1
    total = sum(weights.values())
    if total <= 0:
        return {"available": False, "voters": 0,
                "positive": 0, "neutral": 0, "negative": 0,
                "label": "Ще немає оцінок", "band": "neutral"}
    pct = {k: round((v / total) * 100) for k, v in weights.items()}
    if pct["positive"] >= 60:
        band, label = "positive", "Інвестори задоволені"
    elif pct["negative"] >= 40:
        band, label = "negative", "Є занепокоєння"
    else:
        band, label = "neutral", "Переважно нейтрально"
    return {"available": True, "voters": voters,
            "positive": pct["positive"], "neutral": pct["neutral"],
            "negative": pct["negative"], "label": label, "band": band}


# ──────────────────────────────────────────────────────────────────────────────
# C1/C2 — Feed + summary
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_id}/community/summary")
async def community_summary(asset_id: str, request: Request):
    await _asset_or_404(asset_id)
    user = await _optional_user(request)
    uid = _uid(user) if user else None
    units = await _units_of(asset_id, uid)
    is_holder = units > 0 or _is_admin(user)

    posts_count = await db.lumen_community_posts.count_documents(
        {"asset_id": asset_id, "status": "active"})
    announcements = await db.lumen_community_posts.count_documents(
        {"asset_id": asset_id, "status": "active", "kind": "announcement"})
    discussions = await db.lumen_community_posts.count_documents(
        {"asset_id": asset_id, "status": "active", "kind": "discussion"})
    questions = await db.lumen_community_posts.count_documents(
        {"asset_id": asset_id, "status": "active", "kind": "question"})
    open_polls = await db.lumen_community_polls.count_documents(
        {"asset_id": asset_id, "status": "open"})

    my_pulse = None
    if uid:
        s = await db.lumen_community_sentiment.find_one({"asset_id": asset_id, "holder_id": uid})
        my_pulse = s.get("mood") if s else None

    return {
        "asset_id": asset_id,
        "is_holder": is_holder,
        "is_admin": _is_admin(user),
        "units": units,
        "holders_count": await _holders_count(asset_id),
        "posts_count": posts_count,
        "announcements_count": announcements,
        "discussions_count": discussions,
        "questions_count": questions,
        "open_polls": open_polls,
        "sentiment": await _sentiment(asset_id),
        "my_sentiment": my_pulse,
        "my_reputation": await _reputation(asset_id, uid),
    }


@router.get("/assets/{asset_id}/community/feed")
async def community_feed(asset_id: str, request: Request, filter: str = "all"):
    await _asset_or_404(asset_id)
    user = await _optional_user(request)
    uid = _uid(user) if user else None
    can_see_lounge = (await _units_of(asset_id, uid)) > 0 or _is_admin(user)

    q: dict[str, Any] = {"asset_id": asset_id, "status": "active"}
    if filter in ("announcements", "discussion", "discussions", "question", "questions"):
        kind = filter.rstrip("s")
        q["kind"] = "discussion" if kind == "discussion" else ("question" if kind == "question" else "announcement")
    # holders-only posts hidden from non-holders
    if not can_see_lounge:
        q["visibility"] = "public"

    raw = []
    async for p in db.lumen_community_posts.find(q).sort([("pinned", -1), ("created_at", -1)]).limit(200):
        raw.append(p)
    reps = await _rep_tier_map(asset_id, [p.get("author_id") for p in raw if not p.get("is_operator")])
    items = [_post_out(p, uid=uid, rep=(None if p.get("is_operator") else reps.get(p.get("author_id"))))
             for p in raw]
    return {"asset_id": asset_id, "items": items, "total": len(items),
            "can_see_lounge": can_see_lounge}


@router.get("/community/posts/{post_id}")
async def community_post(post_id: str, request: Request):
    user = await _optional_user(request)
    uid = _uid(user) if user else None
    p = await db.lumen_community_posts.find_one({"id": post_id, "status": "active"})
    if not p:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    if p.get("visibility") == "holders":
        if not ((await _units_of(p["asset_id"], uid)) > 0 or _is_admin(user)):
            raise HTTPException(status_code=403, detail="Доступно лише власникам часток")
    rep = None if p.get("is_operator") else await _reputation(p["asset_id"], p.get("author_id"))
    comments = []
    async for c in db.lumen_community_comments.find(
            {"post_id": post_id, "status": "active"}).sort("created_at", 1).limit(500):
        comments.append(_comment_out(c, uid=uid))
    return {"post": _post_out(p, uid=uid, rep=rep), "comments": comments}


# ──────────────────────────────────────────────────────────────────────────────
# Posting (C1 questions / C2 lounge discussions)
# ──────────────────────────────────────────────────────────────────────────────

class PostIn(BaseModel):
    kind: str = "discussion"           # discussion | question
    title: str = ""
    body: str = ""


@router.post("/assets/{asset_id}/community/posts")
async def create_post(asset_id: str, payload: PostIn, user=Depends(get_current_user)):
    await _asset_or_404(asset_id)
    uid = _uid(user)
    kind = payload.kind if payload.kind in ("discussion", "question") else "discussion"
    title = _clean(payload.title, 200)
    body = _clean(payload.body, 5000)
    if len(body) < 5:
        raise HTTPException(status_code=400, detail="Повідомлення надто коротке")

    units = await _units_of(asset_id, uid)
    is_admin = _is_admin(user)
    # C2 gating: lounge discussions require ownership; questions open to any authed user
    if kind == "discussion":
        visibility = "holders"
        if units <= 0 and not is_admin:
            raise HTTPException(status_code=403,
                                detail="Обговорення в lounge доступні лише власникам часток цього об'єкта")
        if not title:
            raise HTTPException(status_code=400, detail="Вкажіть тему обговорення")
    else:  # question
        visibility = "public"

    doc = {
        "id": f"cp-{uuid.uuid4().hex[:12]}", "asset_id": asset_id,
        "kind": kind, "title": title, "body": body,
        "author_id": uid, "author_name": user.get("name"),
        "is_operator": False, "visibility": visibility,
        "pinned": False, "answer": None, "answered_at": None,
        "comment_count": 0, "reactions": {k: [] for k in REACTIONS},
        "status": "active", "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_community_posts.insert_one(doc)
    rep = await _reputation(asset_id, uid)
    return _post_out(doc, uid=uid, rep=rep)


class CommentIn(BaseModel):
    body: str = ""


@router.post("/community/posts/{post_id}/comments")
async def add_comment(post_id: str, payload: CommentIn, user=Depends(get_current_user)):
    p = await db.lumen_community_posts.find_one({"id": post_id, "status": "active"})
    if not p:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    uid = _uid(user)
    if p.get("visibility") == "holders" and not ((await _units_of(p["asset_id"], uid)) > 0 or _is_admin(user)):
        raise HTTPException(status_code=403, detail="Коментувати lounge можуть лише власники часток")
    body = _clean(payload.body, 3000)
    if len(body) < 2:
        raise HTTPException(status_code=400, detail="Коментар не може бути порожнім")
    doc = {
        "id": f"cc-{uuid.uuid4().hex[:12]}", "post_id": post_id, "asset_id": p["asset_id"],
        "author_id": uid, "author_name": user.get("name"),
        "is_operator": _is_admin(user),
        "body": body, "reactions": {"like": []},
        "status": "active", "created_at": _now(),
    }
    await db.lumen_community_comments.insert_one(doc)
    await db.lumen_community_posts.update_one(
        {"id": post_id}, {"$inc": {"comment_count": 1}, "$set": {"updated_at": _now()}})
    # notify the post author (best-effort) if someone else commented
    try:
        if p.get("author_id") and p["author_id"] != uid and not p.get("is_operator"):
            asset = await db.lumen_assets.find_one({"id": p["asset_id"]})
            await db.lumen_notifications.insert_one({
                "id": str(uuid.uuid4()), "investor_id": p["author_id"],
                "title": "Новий коментар в обговоренні",
                "body": f"Нова відповідь у вашому записі щодо «{(asset or {}).get('title','')}».",
                "kind": "community", "read": False, "created_at": _now(),
            })
    except Exception:
        pass
    return _comment_out(doc, uid=uid)


class ReactIn(BaseModel):
    reaction: str = "like"


@router.post("/community/posts/{post_id}/react")
async def react_post(post_id: str, payload: ReactIn, user=Depends(get_current_user)):
    reaction = payload.reaction if payload.reaction in REACTIONS else "like"
    p = await db.lumen_community_posts.find_one({"id": post_id, "status": "active"})
    if not p:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    uid = _uid(user)
    arr = (p.get("reactions") or {}).get(reaction) or []
    if uid in arr:
        await db.lumen_community_posts.update_one(
            {"id": post_id}, {"$pull": {f"reactions.{reaction}": uid}})
        toggled = False
    else:
        await db.lumen_community_posts.update_one(
            {"id": post_id}, {"$addToSet": {f"reactions.{reaction}": uid}})
        toggled = True
    p = await db.lumen_community_posts.find_one({"id": post_id})
    return {"ok": True, "active": toggled, "post": _post_out(p, uid=uid)}


@router.post("/community/comments/{comment_id}/react")
async def react_comment(comment_id: str, user=Depends(get_current_user)):
    c = await db.lumen_community_comments.find_one({"id": comment_id, "status": "active"})
    if not c:
        raise HTTPException(status_code=404, detail="Коментар не знайдено")
    uid = _uid(user)
    arr = (c.get("reactions") or {}).get("like") or []
    if uid in arr:
        await db.lumen_community_comments.update_one(
            {"id": comment_id}, {"$pull": {"reactions.like": uid}})
    else:
        await db.lumen_community_comments.update_one(
            {"id": comment_id}, {"$addToSet": {"reactions.like": uid}})
    c = await db.lumen_community_comments.find_one({"id": comment_id})
    return {"ok": True, "comment": _comment_out(c, uid=uid)}


# ──────────────────────────────────────────────────────────────────────────────
# C5 — Sentiment pulse (holder sets mood)
# ──────────────────────────────────────────────────────────────────────────────

class MoodIn(BaseModel):
    mood: str = "neutral"


@router.post("/assets/{asset_id}/community/sentiment")
async def set_sentiment(asset_id: str, payload: MoodIn, user=Depends(get_current_user)):
    await _asset_or_404(asset_id)
    uid = _uid(user)
    units = await _units_of(asset_id, uid)
    if units <= 0 and not _is_admin(user):
        raise HTTPException(status_code=403, detail="Оцінювати об'єкт можуть лише власники часток")
    if payload.mood not in MOODS:
        raise HTTPException(status_code=400, detail="mood: positive | neutral | negative")
    await db.lumen_community_sentiment.update_one(
        {"asset_id": asset_id, "holder_id": uid},
        {"$set": {"mood": payload.mood, "units_weight": units or 1.0,
                  "holder_name": user.get("name"), "updated_at": _now()},
         "$setOnInsert": {"id": f"cs-{uuid.uuid4().hex[:10]}", "created_at": _now()}},
        upsert=True)
    return {"ok": True, "my_sentiment": payload.mood, "sentiment": await _sentiment(asset_id)}


# ──────────────────────────────────────────────────────────────────────────────
# C4 — Voting (unit-weighted, advisory)
# ──────────────────────────────────────────────────────────────────────────────

async def _poll_out(poll: dict, *, uid: Optional[str]) -> dict:
    tally = {opt["key"]: {"units": 0.0, "voters": 0} for opt in poll.get("options", [])}
    total_units = 0.0
    total_voters = 0
    my_vote = None
    async for b in db.lumen_community_ballots.find({"poll_id": poll["id"]}):
        ok = b.get("option_key")
        if ok not in tally:
            continue
        w = float(b.get("units_weight") or 0) or 1.0
        tally[ok]["units"] += w
        tally[ok]["voters"] += 1
        total_units += w
        total_voters += 1
        if uid and b.get("voter_id") == uid:
            my_vote = ok
    options = []
    for opt in poll.get("options", []):
        u = tally[opt["key"]]["units"]
        options.append({
            "key": opt["key"], "label": opt["label"],
            "units": round(u), "voters": tally[opt["key"]]["voters"],
            "percent": round((u / total_units) * 100, 1) if total_units > 0 else 0.0,
        })
    return {
        "id": poll["id"], "asset_id": poll["asset_id"],
        "question": poll.get("question", ""),
        "status": poll.get("status", "open"),
        "options": options,
        "total_units": round(total_units), "total_voters": total_voters,
        "my_vote": my_vote,
        "closes_at": _iso(poll.get("closes_at")),
        "created_at": _iso(poll.get("created_at")),
    }


@router.get("/assets/{asset_id}/community/polls")
async def list_polls(asset_id: str, request: Request):
    await _asset_or_404(asset_id)
    user = await _optional_user(request)
    uid = _uid(user) if user else None
    items = []
    async for poll in db.lumen_community_polls.find({"asset_id": asset_id}).sort("created_at", -1).limit(50):
        items.append(await _poll_out(poll, uid=uid))
    return {"asset_id": asset_id, "items": items, "total": len(items)}


class VoteIn(BaseModel):
    option_key: str


@router.post("/community/polls/{poll_id}/vote")
async def cast_vote(poll_id: str, payload: VoteIn, user=Depends(get_current_user)):
    poll = await db.lumen_community_polls.find_one({"id": poll_id})
    if not poll:
        raise HTTPException(status_code=404, detail="Голосування не знайдено")
    if poll.get("status") != "open":
        raise HTTPException(status_code=400, detail="Голосування закрите")
    if payload.option_key not in {o["key"] for o in poll.get("options", [])}:
        raise HTTPException(status_code=400, detail="Невідомий варіант")
    uid = _uid(user)
    units = await _units_of(poll["asset_id"], uid)
    if units <= 0 and not _is_admin(user):
        raise HTTPException(status_code=403, detail="Голосують лише власники часток (вага = ваші units)")
    await db.lumen_community_ballots.update_one(
        {"poll_id": poll_id, "voter_id": uid},
        {"$set": {"option_key": payload.option_key, "units_weight": units or 1.0,
                  "voter_name": user.get("name"), "asset_id": poll["asset_id"],
                  "updated_at": _now()},
         "$setOnInsert": {"id": f"cb-{uuid.uuid4().hex[:10]}", "created_at": _now()}},
        upsert=True)
    return {"ok": True, "poll": await _poll_out(await db.lumen_community_polls.find_one({"id": poll_id}), uid=uid)}


# ──────────────────────────────────────────────────────────────────────────────
# C6 — Leaderboard
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_id}/community/leaderboard")
async def leaderboard(asset_id: str):
    await _asset_or_404(asset_id)
    authors: dict[str, str] = {}
    async for p in db.lumen_community_posts.find(
            {"asset_id": asset_id, "is_operator": {"$ne": True}}, {"author_id": 1, "author_name": 1}):
        if p.get("author_id"):
            authors[p["author_id"]] = p.get("author_name") or "Інвестор"
    async for c in db.lumen_community_comments.find(
            {"asset_id": asset_id, "is_operator": {"$ne": True}}, {"author_id": 1, "author_name": 1}):
        if c.get("author_id"):
            authors.setdefault(c["author_id"], c.get("author_name") or "Інвестор")
    rows = []
    for uid, name in authors.items():
        rep = await _reputation(asset_id, uid)
        rows.append({"user_id": uid, "name": name, **rep})
    rows.sort(key=lambda r: r["score"], reverse=True)
    return {"asset_id": asset_id, "items": rows[:20], "total": len(rows)}


# ──────────────────────────────────────────────────────────────────────────────
# C7 — Admin: Announcements + moderation + poll management
# ──────────────────────────────────────────────────────────────────────────────

class AnnouncementIn(BaseModel):
    title: str
    body: str = ""


@router.post("/admin/assets/{asset_id}/community/announcements")
async def create_announcement(asset_id: str, payload: AnnouncementIn, admin=Depends(require_admin)):
    asset = await _asset_or_404(asset_id)
    title = _clean(payload.title, 200)
    body = _clean(payload.body, 5000)
    if not title:
        raise HTTPException(status_code=400, detail="Вкажіть заголовок оголошення")
    doc = {
        "id": f"cp-{uuid.uuid4().hex[:12]}", "asset_id": asset_id,
        "kind": "announcement", "title": title, "body": body,
        "author_id": _uid(admin), "author_name": admin.get("name"),
        "is_operator": True, "visibility": "public", "pinned": True,
        "answer": None, "answered_at": None,
        "comment_count": 0, "reactions": {k: [] for k in REACTIONS},
        "status": "active", "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_community_posts.insert_one(doc)
    # C7 → notify all current holders
    notified = 0
    async for o in db.lumen_ownerships.find({"asset_id": asset_id}):
        if float(o.get("units_int") or o.get("units") or 0) <= 0:
            continue
        try:
            await db.lumen_notifications.insert_one({
                "id": str(uuid.uuid4()), "investor_id": o["investor_id"],
                "title": f"Оголошення: {title}",
                "body": f"Оператор опублікував оновлення щодо «{asset.get('title','')}».",
                "kind": "community", "read": False, "created_at": _now(),
            })
            notified += 1
        except Exception:
            pass
    logger.info("ANNOUNCEMENT %s → notified %d holders", asset_id, notified)
    return {"ok": True, "post": _post_out(doc, uid=_uid(admin)), "notified": notified}


class AnswerIn(BaseModel):
    answer: str


@router.post("/admin/community/posts/{post_id}/answer")
async def operator_answer(post_id: str, payload: AnswerIn, admin=Depends(require_admin)):
    p = await db.lumen_community_posts.find_one({"id": post_id})
    if not p:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    answer = _clean(payload.answer, 3000)
    if len(answer) < 2:
        raise HTTPException(status_code=400, detail="Відповідь не може бути порожньою")
    await db.lumen_community_posts.update_one(
        {"id": post_id}, {"$set": {"answer": answer, "answered_at": _now(), "updated_at": _now()}})
    try:
        if p.get("author_id"):
            asset = await db.lumen_assets.find_one({"id": p["asset_id"]})
            await db.lumen_notifications.insert_one({
                "id": str(uuid.uuid4()), "investor_id": p["author_id"],
                "title": "Оператор відповів",
                "body": f"Відповідь на ваше питання щодо «{(asset or {}).get('title','')}».",
                "kind": "community", "read": False, "created_at": _now(),
            })
    except Exception:
        pass
    return {"ok": True, "post": _post_out(await db.lumen_community_posts.find_one({"id": post_id}), uid=_uid(admin))}


@router.post("/admin/community/posts/{post_id}/pin")
async def toggle_pin(post_id: str, _=Depends(require_admin)):
    p = await db.lumen_community_posts.find_one({"id": post_id})
    if not p:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    await db.lumen_community_posts.update_one(
        {"id": post_id}, {"$set": {"pinned": not bool(p.get("pinned")), "updated_at": _now()}})
    return {"ok": True, "pinned": not bool(p.get("pinned"))}


@router.delete("/admin/community/posts/{post_id}")
async def delete_post(post_id: str, _=Depends(require_admin)):
    res = await db.lumen_community_posts.update_one(
        {"id": post_id}, {"$set": {"status": "hidden", "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    return {"ok": True}


@router.delete("/admin/community/comments/{comment_id}")
async def delete_comment(comment_id: str, _=Depends(require_admin)):
    c = await db.lumen_community_comments.find_one({"id": comment_id})
    if not c:
        raise HTTPException(status_code=404, detail="Коментар не знайдено")
    await db.lumen_community_comments.update_one(
        {"id": comment_id}, {"$set": {"status": "hidden"}})
    await db.lumen_community_posts.update_one(
        {"id": c["post_id"]}, {"$inc": {"comment_count": -1}})
    return {"ok": True}


class PollIn(BaseModel):
    question: str
    options: list[str] = []
    closes_in_days: Optional[int] = None


@router.post("/admin/assets/{asset_id}/community/polls")
async def create_poll(asset_id: str, payload: PollIn, admin=Depends(require_admin)):
    await _asset_or_404(asset_id)
    question = _clean(payload.question, 300)
    opts = [_clean(o, 120) for o in (payload.options or []) if _clean(o, 120)]
    if not question or len(opts) < 2:
        raise HTTPException(status_code=400, detail="Потрібне питання і щонайменше 2 варіанти")
    options = [{"key": f"opt{i+1}", "label": label} for i, label in enumerate(opts[:6])]
    closes_at = None
    if payload.closes_in_days and payload.closes_in_days > 0:
        closes_at = _now() + timedelta(days=int(payload.closes_in_days))
    doc = {
        "id": f"poll-{uuid.uuid4().hex[:10]}", "asset_id": asset_id,
        "question": question, "options": options, "status": "open",
        "created_by": _uid(admin), "closes_at": closes_at,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_community_polls.insert_one(doc)
    return {"ok": True, "poll": await _poll_out(doc, uid=None)}


@router.post("/admin/community/polls/{poll_id}/close")
async def close_poll(poll_id: str, _=Depends(require_admin)):
    res = await db.lumen_community_polls.update_one(
        {"id": poll_id}, {"$set": {"status": "closed", "closed_at": _now(), "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Голосування не знайдено")
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Indexes + demo seed (idempotent)
# ──────────────────────────────────────────────────────────────────────────────

async def ensure_community_indexes() -> None:
    await db.lumen_community_posts.create_index([("asset_id", 1), ("status", 1), ("pinned", -1), ("created_at", -1)])
    await db.lumen_community_comments.create_index([("post_id", 1), ("status", 1), ("created_at", 1)])
    await db.lumen_community_polls.create_index([("asset_id", 1), ("status", 1)])
    await db.lumen_community_ballots.create_index([("poll_id", 1), ("voter_id", 1)], unique=True)
    await db.lumen_community_sentiment.create_index([("asset_id", 1), ("holder_id", 1)], unique=True)


async def seed_community_demo() -> dict:
    """Idempotent: seed lounge discussions, announcements, a poll and mood pulses
    using REAL holders (from lumen_ownerships)."""
    if await db.lumen_community_posts.count_documents({}) > 0:
        return {"seeded": False, "reason": "already present"}

    created = {"posts": 0, "comments": 0, "polls": 0, "pulses": 0}

    # Map asset → list of (holder_id, holder_name, units)
    holders_by_asset: dict[str, list] = {}
    async for o in db.lumen_ownerships.find({}):
        units = float(o.get("units_int") or o.get("units") or 0)
        if units <= 0:
            continue
        u = await db.users.find_one({"$or": [{"user_id": o["investor_id"]}, {"id": o["investor_id"]}]})
        name = (u or {}).get("name") or "Інвестор"
        holders_by_asset.setdefault(o["asset_id"], []).append((o["investor_id"], name, units))

    async def _add_post(asset_id, kind, title, body, author, name, is_op, visibility, pinned=False, answer=None):
        doc = {
            "id": f"cp-{uuid.uuid4().hex[:12]}", "asset_id": asset_id, "kind": kind,
            "title": title, "body": body, "author_id": author, "author_name": name,
            "is_operator": is_op, "visibility": visibility, "pinned": pinned,
            "answer": answer, "answered_at": _now() if answer else None,
            "comment_count": 0, "reactions": {k: [] for k in REACTIONS},
            "status": "active", "created_at": _now(), "updated_at": _now(),
        }
        await db.lumen_community_posts.insert_one(doc)
        created["posts"] += 1
        return doc

    # Operator announcement + holder lounge discussion for assets that have holders
    SEED = {
        "asset-podilskyi": {
            "announcement": ("Підписано договір оренди паркінгу",
                             "Підземний паркінг передано в управління оператору з фіксованим платежем — +1.2% до річної дохідності SPV."),
            "discussion": ("Коли очікувати першу виплату?",
                           "Колеги-співвласники, за моделлю перша виплата після введення в експлуатацію. Хтось уточнював у оператора точний місяць?"),
            "question": ("Чи застрахований об'єкт на період будівництва?",
                         None),
            "poll": ("Чи підтримуєте подовження договору з керуючою компанією ще на 2 роки?",
                     ["Так, підтримую", "Ні, шукати іншу", "Утримаюсь"]),
        },
        "asset-lavr-tc": {
            "announcement": ("Заповнюваність зросла до 92%",
                             "Підписано якірного орендаря на 1 850 м² (5-річний договір). Орендний потік стабільний."),
            "discussion": ("Думки щодо реконцепції фудкорту?",
                           "Оператор пропонує оновити фудкорт. Це +9% доходу за моделлю, але капітальні витрати. Як голосуємо?"),
            "question": ("Який середній строк договорів з орендарями?", None),
            "poll": ("Реінвестувати частину доходу в реконцепцію фудкорту?",
                     ["Так, реінвестувати", "Ні, виплачувати повністю"]),
        },
        "asset-stoyanka-land": {
            "announcement": ("Подано документи на зміну цільового призначення",
                             "Це ключовий драйвер переоцінки. Очікуємо рішення районної адміністрації."),
            "discussion": ("Хто ще тримає частку зі старту раунду?",
                           "Цікаво познайомитись зі співвласниками ділянки. Який у вас горизонт очікувань?"),
            "question": None,
            "poll": None,
        },
    }

    for asset_id, cfg in SEED.items():
        holders = holders_by_asset.get(asset_id) or []
        admin = await db.users.find_one({"email": "admin@atlas.dev"})
        admin_id = (admin or {}).get("user_id") or (admin or {}).get("id")
        # Announcement (operator)
        if cfg.get("announcement"):
            t, b = cfg["announcement"]
            await _add_post(asset_id, "announcement", t, b, admin_id, "Atlas Admin", True, "public", pinned=True)
        # Question (public) — author = first holder or demo client
        if cfg.get("question"):
            t, _ = cfg["question"]
            if holders:
                a_id, a_name, _u = holders[0]
            else:
                demo = await db.users.find_one({"email": "client@atlas.dev"})
                a_id, a_name = (demo or {}).get("user_id"), (demo or {}).get("name")
            q = await _add_post(asset_id, "question", t, t, a_id, a_name, False, "public")
            # operator answer to first question
            await db.lumen_community_posts.update_one(
                {"id": q["id"]}, {"$set": {"answer": "Так, діє поліс CAR (Contractor's All Risks) на весь період будівництва. Копію додамо в документи.", "answered_at": _now()}})
        # Lounge discussion (holders) — needs a holder author
        if cfg.get("discussion") and holders:
            t, b = cfg["discussion"]
            a_id, a_name, _u = holders[0]
            post = await _add_post(asset_id, "discussion", t, b, a_id, a_name, False, "holders")
            # a second holder comments if available
            if len(holders) > 1:
                c_id, c_name, _u2 = holders[1]
                await db.lumen_community_comments.insert_one({
                    "id": f"cc-{uuid.uuid4().hex[:12]}", "post_id": post["id"], "asset_id": asset_id,
                    "author_id": c_id, "author_name": c_name, "is_operator": False,
                    "body": "Я писав оператору — орієнтовно перший квартал після здачі. Тримаю частку від старту.",
                    "reactions": {"like": [a_id]}, "status": "active", "created_at": _now(),
                })
                await db.lumen_community_posts.update_one(
                    {"id": post["id"]}, {"$inc": {"comment_count": 1}})
                created["comments"] += 1
        # Poll (admin) + a couple of unit-weighted ballots
        if cfg.get("poll"):
            q, opts = cfg["poll"]
            options = [{"key": f"opt{i+1}", "label": l} for i, l in enumerate(opts)]
            poll = {
                "id": f"poll-{uuid.uuid4().hex[:10]}", "asset_id": asset_id,
                "question": q, "options": options, "status": "open",
                "created_by": admin_id, "closes_at": _now() + timedelta(days=14),
                "created_at": _now(), "updated_at": _now(),
            }
            await db.lumen_community_polls.insert_one(poll)
            created["polls"] += 1
            for idx, (h_id, h_name, h_units) in enumerate(holders[:3]):
                await db.lumen_community_ballots.insert_one({
                    "id": f"cb-{uuid.uuid4().hex[:10]}", "poll_id": poll["id"], "asset_id": asset_id,
                    "voter_id": h_id, "voter_name": h_name,
                    "option_key": options[idx % len(options)]["key"],
                    "units_weight": h_units, "created_at": _now(),
                })
        # Sentiment pulses from holders
        for idx, (h_id, h_name, h_units) in enumerate(holders[:4]):
            mood = "positive" if idx % 3 != 2 else "neutral"
            await db.lumen_community_sentiment.update_one(
                {"asset_id": asset_id, "holder_id": h_id},
                {"$set": {"mood": mood, "units_weight": h_units, "holder_name": h_name, "updated_at": _now()},
                 "$setOnInsert": {"id": f"cs-{uuid.uuid4().hex[:10]}", "created_at": _now()}},
                upsert=True)
            created["pulses"] += 1

    logger.info("COMMUNITY (Phase C) demo seed: %s", created)
    return {"seeded": True, **created}
