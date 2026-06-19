"""
Runtime layer — публичный alias-роутер для capability matrix.

Контракт: runtime-client (web + expo) пингует `/api/runtime/capabilities`
для bootstrap'a feature-флагов. Endpoint существовал только под
`/api/integrations/capabilities` и `/api/integrations/manifest`, что вызывало
404 при ожидании consumer'а получить ответ под `/api/runtime/*`.

Этот модуль НЕ добавляет новой бизнес-логики — он переэкспортирует те же
обработчики из `integrations_api` под альтернативным prefix'ом. Source of
truth остаётся `integrations/registry.py`.

Wired в server.py одной строкой:

    fastapi_app.include_router(runtime_layer.router, prefix="/api")
"""
from __future__ import annotations

from fastapi import APIRouter

from integrations_api import (
    get_capability_matrix,
    get_capability_manifest,
)

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/capabilities")
async def runtime_capabilities() -> dict:
    """Alias для `/api/integrations/capabilities`.

    Возвращает идентичный shape — runtime-client'у не важен путь, важен
    контракт. Хранение единого хэндлера ниже исключает drift.
    """
    return await get_capability_matrix()


@router.get("/manifest")
async def runtime_manifest() -> dict:
    """Alias для `/api/integrations/manifest`.

    Используется при boot'е runtime-client (web + expo) для определения
    политики gate'а (hard|soft) per capability + TTL обновления.
    """
    return await get_capability_manifest()
