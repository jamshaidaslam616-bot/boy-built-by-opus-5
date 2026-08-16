# COSTS.md — what a trade actually costs, measured

**Phase:** P0 · **Measured:** 2026-08-08 00:51 UTC · **Source:** live Exness MT5 terminal, read-only
**Reproduce:** `.venv\Scripts\python.exe scripts\p0_recon.py`

Har number neeche terminal se **parha gaya** hai. Jo nahi parha ja saka woh saaf "NOT MEASURED"
likha hai — plausible default se bhara **nahi** gaya. Yeh is poori file ka maqsad hai.

---

## 1. Account — jo terminal mein pehle se logged in tha

| | |
|---|---|
| Login | `472250693` |
| Server | `Exness-MT5Trial16` |
| Company | Exness Technologies Ltd |
| Trade mode | **DEMO** |
| Currency | USD |
| Balance / Equity | $23,658.72 |
| Leverage | 1:2000 |
| Symbol path | `Zero\Forex\XAUUSD` → **Zero account confirmed** |

Yeh script ne **credentials pass nahi kiye** — sirf attach kiya. Teen bot projects ek hi terminal
share karte hain aur jo process aakhir mein `initialize(login=...)` kare woh baqi sab ko tor deta
hai. `mt5_read.py` mein login ka koi raasta hai hi nahi.

> **Note:** demo balance $23,658.72 hai magar sizing ka basis aap ka **$10,000** wala figure hai.
> Balance sizing mein use nahi hoga — live equity hoga, aur limits percentage mein hain.

---

## 2. Contract specs — measured, kahin hardcode nahi

| | XAUUSD | XAGUSD |
|---|---|---|
| Contract size | 100 oz | 5,000 oz |
| Digits / point | 3 / 0.001 | 3 / 0.001 |
| **Value per point per lot** | **$0.10** | **$5.00** |
| Volume min / step / max | 0.01 / 0.01 / 200.0 | 0.01 / 0.01 / 200.0 |
| Stops level / freeze level | 0 / 0 | 0 / 0 |
| Notional per lot @ measured price | $434,233 | $317,785 |
| Min position notional (0.01 lot) | $4,342 | $3,178 |

**Arithmetic cross-check passed on both.** Hamara `value_per_point_per_lot` aur broker ka apna
`order_calc_profit` — 1.000 price move on 1.00 lot:

| | Ours | Broker | |
|---|---|---|---|
| XAUUSD | $100.00 | $100.00 | **AGREE** |
| XAGUSD | $5,000.00 | $5,000.00 | **AGREE** |

Agar yeh kabhi disagree karein to system ki har position size usi factor se ghalat hai. Isliye yeh
ek permanent test banega.

**`stops_level = 0`** ka matlab: broker minimum stop distance enforce nahi karta. Yaani hamari
minimum stop distance hamari apni volatility logic se aayegi, broker ke inkaar se nahi.

---

## 3. Swap / carry — **yeh is account ki sab se bari cost hai**

| | XAUUSD | XAGUSD |
|---|---|---|
| Swap long | −523.8 points/night = **−$52.38/lot/night** | −7.8 points/night = **−$39.00/lot/night** |
| Swap short | 0.0 points = **$0.00** | 0.0 points = **$0.00** |
| Swap mode | 1 | 1 |
| Triple swap day | **Wednesday** (MT5 weekday 3) | **Wednesday** (MT5 weekday 3) |
| **Carry, long, % of notional/yr** | **−5.66%** | **−5.76%** |
| **Carry, short, % of notional/yr** | **+0.00%** | **+0.00%** |

Teen baatein jo yahan se nikalti hain:

**(a) Triple swap Wednesday hai, Thursday nahi.** MT5 ka `ENUM_DAY_OF_WEEK` **0=Sunday** hai,
0=Monday nahi. `swap_rollover3days = 3` ka matlab Wednesday hai. Purane project ke `DECISIONS.md`
mein "Thursday" likha tha — woh 0=Monday maan kar ki gayi mapping thi aur **ghalat** thi. Ek long
position jo Wednesday ki server-midnight paar kare woh ~$157/lot deti hai, $52 nahi.

**(b) Swap static nahi hai — woh hilta hai.** Purane project ne 2026-08-07 ko −509.9 points naapa
tha; aaj woh **−523.8** hai. Ek din mein 2.7% change. Iska seedha natija: **swap har run par live
parha jayega, kabhi cache nahi hoga.**

**(c) Short side ko carry credit milta hi nahi.** Yeh sab se ahem structural fact hai. Ek normal
market mein short ko financing credit milta hai. Yahan woh $0.00 hai — broker poora carry rakh leta
hai. Iska asar Section 5 mein hai.

---

## 4. Spread — **NOT MEASURED. Market band tha.**

Script chalte waqt market **band** tha — aakhri tick Friday 2026-08-07 20:57 UTC ka tha, 3.90 ghante
purana.

| | Reading | Status |
|---|---|---|
| XAUUSD spread | 50 points ($5.00/lot) | **SUSPECT — closed session** |
| XAGUSD spread | **0 points ($0.00/lot)** | **INVALID — a zero spread is not a price** |

XAGUSD ka `bid == ask == 63.557` — yeh frozen close print hai, spread nahi.

**Yeh bilkul wohi ghalti hai jo purane project ko mehngi pari.** Wahan archive ke 15% bars par
spread zero record tha, aur woh un bars par trade ko *muft* bana deta tha — jo kisi bhi strategy ko
alpha dikha deta jo un bars par concentrate kare. Structural validity aur sach hona do alag cheezein
hain.

Isliye `mt5_read.feed_state()` ab session status aur tick age **alag alag** report karta hai, aur
recon script closed market par har spread number ko `SUSPECT` mark karta hai.

**OPEN ITEM — P0 abhi mukammal nahi:** market khulne par (Sunday ~21:00–22:00 UTC) yeh script dobara
chalegi, aur behtar yeh ke London/NY overlap (13:00–17:00 UTC) mein bhi, taake session ke hisab se
spread distribution mile — ek single reading nahi.

---

## 5. B3 (gold–silver spread) — pehla real setback

Plan mein B3 meri #5 ranked idea thi aur "sab se under-exploited" kaha tha. **P0 ne uske against
pehla sakht number diya hai.**

Spread trade ek leg long aur ek short hoti hai. Is account par short **koi carry credit nahi** deta,
to jo bhi leg long hai woh apna poora carry bharta hai aur short leg usme se kuch wapas nahi karti:

| Direction | Carry drag |
|---|---|
| Long gold / short silver | **−5.66% per year** |
| Long silver / short gold | **−5.76% per year** |

Ek mean-reversion trade jo hafton chalti hai, woh ~5.7%/saal nahi bhar sakti. Ratio ko itna move
karna paregi ke sirf carry cover ho — aur uske baad profit shuru ho.

**Yeh idea mara nahi, magar venue ke saath bandh gaya.** Futures par short leg carry **kamati** hai,
to pair taqreeban carry-neutral ho jaati hai. Yaani:

> **B3 ka test CFD par karna waqt zaya karna hoga.** Agar B3 test hogi to futures data par hogi, aur
> agar chalti hai to execution bhi futures par hoga. Yeh Section 6 ke switch trigger mein add ho
> chuka hai.

---

## 6. Venue switch trigger — **abhi likha ja raha hai, kisi natije se pehle**

Plan (Part 0b #1) kehta hai trigger natije se pehle likha jayega taake baad mein rationalise na ho
sake. Yeh raha:

> ### ⚠ AMENDED 2026-08-09 — yeh trigger jaise likha tha, **ghalat tha**
>
> Neeche ka trigger sirf **carry** dekhta tha. Usne yeh check hi nahi kiya ke naya venue
> position **express bhi kar sakta hai ya nahi**. `FINDINGS.md` F10 ne naapa ke ek MGC micro
> contract $10,000 account par 5% vol target ke liye **12.8× bara** hai, aur GC **128×**.
> Yaani trigger fire ho jata aur hum ek aise venue par chale jate jahan trade karna hi
> mumkin nahi.
>
> **Amended trigger — dono shart poori honi chahiye:**
>
> 1. Neeche wali carry conditions mein se koi, **AUR**
> 2. **Capital ≥ ~$65,000** (10% vol target par) ya **~$128,000** (5% par) — taake ek MGC
>    contract ek maqool position ho, 13× oversized na ho.
>
> **Abhi ka faisla: CFD par raho.** Iski financing achhi nahi hai aur markup asli hai — magar
> $10,000 par futures carry ke faide ke bawajood **na-qabil-e-istemal** hain. CFD ka 0.01-lot
> minimum (1 oz) MGC se **10× barik** hai, aur wahi ek wajah hai ke yeh strategy is account
> size par implement ho sakti hai.

**Original trigger (carry conditions — ab condition 1 of 2):**

1. Koi surviving strategy **long-biased** ho aur average hold **> 2 nights** — kyunke −5.66%/saal
   carry us edge ko kha jayega.
2. Koi surviving strategy **do-legged** ho (B3 gold–silver, ya koi bhi pair) — kyunke CFD par short
   leg carry wapas nahi karti aur futures par karti hai. **Yeh already trigger ho chuka hai agar B3
   test hoti hai.**
3. Order flow (E1–E3) research se koi feature bache jo execution ke waqt bhi chahiye — CFD ka volume
   broker ka tick count hai, market ka nahi.

**CFD par rehna theek hai agar:**

- Surviving strategy **short-biased** ho (short par carry $0 hai — na credit, na charge), ya
- **intraday** ho, rollover se pehle flat, yaani carry lagti hi nahi.

**Faisla P4 ke baad hoga, in rules par — meri us waqt ki raay par nahi.**

---

## 7. Ab tak ka cost model (jo P3/P4 use karega)

| Component | Value | Source | Confidence |
|---|---|---|---|
| Value per point per lot | XAU $0.10 · XAG $5.00 | Terminal, cross-checked vs `order_calc_profit` | **MEASURED** |
| Swap long | XAU −$52.38 · XAG −$39.00 /lot/night | Terminal, live read | **MEASURED** (re-read every run) |
| Swap short | $0.00 both | Terminal, live read | **MEASURED** |
| Triple swap day | Wednesday | Terminal, `swap_rollover3days=3`, 0=Sunday | **MEASURED** |
| Spread | — | Market closed at measurement time | **NOT MEASURED — blocks P3** |
| **Commission** | **$11.00/lot round turn, charged wholly on OPEN** | **598 real fills, deal history** | **MEASURED** |
| Slippage | — | Needs real fills | **NOT MEASURED** |

**Ab sirf ek number missing hai — spread.** Jab tak woh na mile, backtest ke natije "provisional"
likhe jayenge, kyunke ek galat cost model chupke se har result ko behtar dikhata hai.

### Commission — RESOLVED 2026-08-08, deal history se

`scripts/p0_commission_from_history.py` ne account ki **pehle se maujood 1,196 XAUUSD deals** parhi
(purane projects ki testing se). Koi nayi trade bhejne ki zaroorat nahi pari.

| | Measured |
|---|---|
| XAUUSD, on **open** | **$11.0000 per lot** — 598 fills, har ek bilkul yehi |
| XAUUSD, on **close** | **$0.00** — commission line hai hi nahi |
| **Round turn** | **$11.00 per lot** = **0.253 bp** of notional |
| BTCUSD (comparison) | $8.80 per lot, bhi wholly on open |

**Do baatein isme se:**

**(a) Total sahi tha, shape ghalat thi.** Purana project `$5.50 per lot per side` maan raha tha, jo
round turn par $11.00 banta hai — **theek wohi number**. To koi backtest result nahi badalta. Lekin
woh ittefaq tha, measurement nahi: agar Exness `$5.50` waqai per-side hota to round turn $11.00 hi
rehta, magar agar woh `$5.50` on-open-only hota to hum 2× over-costing kar rahe hote.

**(b) Is account par commission poori OPEN par lagti hai.** Yeh gold aur BTCUSD dono par confirmed
hai. Iska matlab: ek position kholte hi poora commission ada ho jata hai, chahe woh do minute chale
ya do hafte. **Isliye commission ka bojh short holds par proportionally zyada hai** — jo M15/scalping
family ke against ek aur number hai, aur daily-hold family ke haq mein.

Cost model mein `commission_bp = 0.25` pehle se yehi tha (0.253 se rounded), to `BASELINE.md` ka
Sharpe **+0.502 unchanged** hai.
