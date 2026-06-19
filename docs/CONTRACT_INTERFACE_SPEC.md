# LUMEN — Smart Contract Interface Specification (для Solidity-розробника / аудитора)

**Версія:** H2.2 · **Статус:** specification only — Solidity НЕ написано навмисно.

> **Головне архітектурне правило (не порушувати):**
> **Pool OS = source of truth.** Смарт-контракт — це лише **платіжний escrow + NFT mirror**.
> Контракт **НЕ** містить: дивідендів, доходу, резервів, податків, AML/KYC/PEP, cash audit,
> revenue events, реєстру власності як джерела істини. Усе це вже живе в Pool OS (USD-ядро).

Цей документ — ТЗ, яке передається професійному Solidity-розробнику/аудитору. Backend
(`lumen_pool_gateways.py`, `lumen_pool_os.py`) уже готовий приймати події контракту через
gateway-шар. Контракт можна спроєктувати/переписати без жодних змін у backend, доки він
відповідає інтерфейсу подій нижче.

---

## 1. Що контракт РОБИТЬ (рівно 5 речей)

1. **Приймає USDT/USDC** на конкретний пул (escrow), фіксуючи `wallet · amount · timestamp · contributionRef`.
2. **Блокує переповнення:** `require(raised + amount <= hardCap)`.
3. **Керує статусом пулу:** `OPEN → PAUSED → FUNDED → RELEASED → CLOSED` (+ refund-режим).
4. **Повертає кошти** (`refund`) якщо soft cap не досягнуто або проєкт скасовано.
5. **NFT (ERC-721/1155):** mint сертифіката та **transfer** (OTC передача права власності).

## 2. Чого в контракті бути НЕ повинно
дивіденди · розподіл доходу · резерви · податки · AML/KYC/PEP · cash audit · revenue events ·
розрахунок частки/дохідності · бізнес-логіка фонду. (Усе — у Pool OS.)

---

## 3. Escrow-контракт — інтерфейс

```solidity
interface ILumenPoolEscrow {
    // статуси: 0 OPEN, 1 PAUSED, 2 FUNDED, 3 RELEASED, 4 CLOSED, 5 REFUNDING
    function deposit(uint256 amount, bytes32 contributionRef) external; // require(raised+amount<=hardCap)
    function pause() external;     // onlyAdmin
    function resume() external;    // onlyAdmin
    function close() external;     // onlyAdmin -> FUNDED/CLOSED
    function release() external;   // onlyAdmin -> переказ зібраного на treasury
    function refund(bytes32 contributionRef) external; // onlyAdmin (soft-cap fail/cancel)

    event Deposited(bytes32 indexed contributionRef, address indexed investor, uint256 amount);
    event Refunded (bytes32 indexed contributionRef, address indexed investor, uint256 amount);
    event StatusChanged(uint8 status);
}
```

**Параметри конструктора:** `token (USDT/USDC) · treasury · hardCap · minDeposit · softCap`.
**Ключова інваріанта:** `totalDeposited <= hardCap` (єдиний cap; той самий, що `hard_cap_usd` у Pool OS).

## 4. NFT-сертифікат — інтерфейс

```solidity
interface ILumenCertificateNFT {            // ERC-721 (або ERC-1155)
    function mint(address to, string calldata metadataURI) external returns (uint256 tokenId); // onlyAdmin
    function transferFrom(address from, address to, uint256 tokenId) external;                  // owner|admin
    function burn(uint256 tokenId) external;                                                    // onlyAdmin

    event Minted  (address indexed to, uint256 indexed tokenId, string uri);
    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
}
```

**NFT містить лише:** `pool_id · allocation_id · owner_wallet · metadata_uri`.
**NFT НЕ містить:** yield · balance · profit · ownership database. NFT = дзеркало сертифіката, не реєстр.

### 4.1 Обов'язкові події (backend слухає саме їх)

```solidity
event CertificateMinted(
    uint256 indexed tokenId,
    bytes32 indexed poolId,
    bytes32 indexed allocationId,
    uint256 units,
    address holder
);
event CertificateTransferred(
    uint256 indexed tokenId,
    address indexed from,
    address indexed to
);
```

> **Правило власності (зафіксовано):** дивіденди нараховуються **поточному holder NFT на
> snapshot date**, а не старому `investor_id`. NFT має бути **transferable**. Якщо NFT
> опинився на гаманці, не привʼязаному до LUMEN-акаунта — виплата не втрачається, а
> паркується у статус `claimable_pending_wallet_link`.

---

## 5. Контракт події → Pool OS (вже реалізований seam)

| Подія контракту | Backend endpoint (вже є) | Ефект у Pool OS |
|---|---|---|
| `Deposited` | `POST /api/admin/crypto/webhook/deposit` `{contribution_ref, tx_hash, wallet_address, amount_token, chain_id}` | → unified `confirm_contribution` (USD, hard-cap guard, units, ledger, cash movement, allocation, certificate) |
| `Refunded` | `POST /api/admin/pool-contributions/{id}/refund` *(існуючий)* | повернення внеску |
| `Minted` / `Transfer` | (H2.4 NFT Registry — наступний шар) | дзеркалить `nft_token_id`, новий власник → `transfer_pool_allocation` |

**Pool OS бачить лише `{gateway, amount_usd}`** — стейблкойн конвертується 1:1 у USD на gateway-шарі.
Контракт ніколи не диктує частку/дохідність — лише факт і суму депозиту.

---

## 6. Передумови деплою (env)
`LUMEN_POOL_CONTRACT_ADDRESS` · `LUMEN_POOL_CHAIN_ID` · `LUMEN_TOKEN_USDT` · `LUMEN_TOKEN_USDC` ·
`LUMEN_POOL_IBAN` / `LUMEN_POOL_BENEFICIARY` (fiat). Поки не задані — gateway повертає плейсхолдери,
а backend працює (крипто-депозити підтверджуються через admin/indexer webhook).

## 7. Порядок далі
H2.3 Wallet Registry → H2.4 NFT Registry → **тільки потім** передати цей spec Solidity-розробнику
(ERC-721 · USDT deposits · hard/soft cap · refund · pause · release · NFT mint · NFT transfer).
