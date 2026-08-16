# STATUS.md — project kahan khara hai

**Updated:** 2026-08-09 · **Phases done:** P0–P5 · **Tests:** 32 green · **Prereg chain:** intact, 27 entries, 46 trials counted

---

## 0. FINAL VERDICT (2026-08-10, P12 ke baad)

**Masla gold nahi tha. Masla is broker ka kiraya hai.**

Wahi trend rule 19 markets par chalaya (FX, metals, energy, indices, crypto). Costs ke baad
**mean single-market Sharpe −0.20** hai, aur portfolio **paisa haarta hai** (−$89 se −$141
per $10,000).

Wajah: **yeh broker har instrument par, har taraf, 2% se 31%/saal kiraya leta hai** —
XAUUSD long −5.68%, US500 long −8.76%, BTCUSD long −9.28%, USDCHF short −5.74%,
**USOIL short −31.38%**. Ek trend system ko position **rakhni** parti hai. Yeh do cheezein
ek saath nahi chal sakteen.

**Aur gold ka +0.438 selection tha** — 19 markets par wahi rule chalao to koi na koi 0.4+
dikhayega. Random-entry control ne yeh pehle din se keh diya tha (z = +1.32, kabhi
significant nahi). Main poore project mein us ke ird-gird raaste dhoondta raha; woh theek
tha.

**Kya cheez yeh math badal degi:**

| | Ab | Kab |
|---|---|---|
| Financing 2–31%/yr, har taraf | Har strategy ko maar deti hai | — |
| Futures (koi financing nahi) | 1 MGC contract $10k par **12.8× bara** | **~$65,000 capital par** |
| Intraday (raat bhar hold nahi) | Financing lagti hi nahi | Order flow data chahiye |

---

## 1. Ek jumle mein

**Koi validated edge nahi mila.** Sab se behtar candidate — gold par 5-speed long-only trend
ensemble — 12.6 saal ke data par, owner ki **nayi 20% drawdown limit** ke andar
**~$209/saal per $10,000** deta hai, **aur woh har out-of-sample robustness test fail karta
hai.**

Woh $209 **peshangoi nahi hai.** Woh ek aisi strategy ki tareekhi kaarkardagi hai jo gauntlet
se guzri hi nahi (control z **+1.32**, Deflated Sharpe **0.14** — apne hi rotation se alag
nahi).

### Risk limits — updated 2026-08-10

| Limit | Value | |
|---|---|---|
| Risk per trade | 0.5% | unchanged, owner-set |
| Daily loss stop | 3% | unchanged, owner-set |
| **Max drawdown (live halt)** | **20%** | **raised from 10% on owner's explicit authorisation** |
| **Backtest drawdown gate** | **12.5%** | = 20% / 1.58, see F13 |
| Max concurrent positions | 1 | unchanged |

Owner ne number mujh par chhora tha; **20% block-bootstrap se chuna gaya, andaze se nahi**.
Backtest gate sakht **hua** (15% → 12.5%), kyunke ek path drawdown ko 1.58× kam dikhata hai.

---

## 2. Kya bana

| Cheez | Halat |
|---|---|
| Read-only MT5 module (attach-only, koi order function nahi) | ✅ |
| Falsification harness — purged walk-forward, 3 random controls, Deflated Sharpe | ✅ **apne aap par proven** |
| Hash-chained pre-registration log | ✅ intact, 27 entries |
| Data: gold D1/H4/H1/M15 + silver D1, quality-gated | ✅ |
| Macro: FRED real yields + broad dollar, point-in-time aligned | ✅ |
| CFTC COT gold + silver, release-lag aligned | ✅ |
| Cost model — commission **measured**, carry **measured**, spread **abhi assumed** | ⚠ |
| **Trading bot** | ❌ **jaan-boojh kar nahi banaya** |

Bot isliye nahi bana ke us mein daalne layak koi cheez nahi mili. Yeh plan ka original
tarteeb tha aur woh sahi sabit hua.

---

## 3. Lab par kyun bharosa kiya ja sakta hai

Ek hi pipeline, do farzi duniyaon par:

| | Planted edge | Pure random walk |
|---|---|---|
| Control z-score | **+14.28** | +0.95 |
| Deflated Sharpe | **1.0000** | 0.0006 |
| Verdict | **PASS** | **FAIL** |

Yeh test suite mein permanent hai. Agar yeh kabhi fail ho, koi natija qabil-e-aitmaad nahi.

---

## 4. Har cheez jo test hui, aur uska anjaam

| # | Idea | Anjaam | Kahan |
|---|---|---|---|
| A1a | Time-series momentum (3 speeds) | FAIL — best Sharpe +0.420 | F8 |
| A1b | MA crossover (3 combos) | FAIL — best +0.423 | F8 |
| A1c | Confidence-scaled trend (2) | FAIL — +0.361 | F8 |
| A10 | Volatility breakout (2) | FAIL — +0.081 | F8 |
| B1 | Real yield regime (2) | FAIL — +0.004 | F5, F8 |
| B2 | Dollar regime (2) | FAIL — +0.104 | F5, F8 |
| A1×B1 | Yield-gated trend (2) | FAIL — +0.295 | F8 |
| A1×B2 | Dollar-gated trend (2) | FAIL — +0.326 | F8 |
| B3 | Gold–silver reversion (2) | **FAIL badly** — −0.688, 75% DD | F8 |
| B7 | COT contrarian | **Sign ULTA** — dawa support nahi hota | F6 |
| — | Triple-swap-night avoidance | FAIL — −0.099 Sharpe | F7 |
| P4 | 5-speed ensemble | FAIL, magar behtareen: $128 → **$151** | F10 |
| P4b | Gold + silver | **FAIL — Calmar −32%** | F11 |

**26 parameter combinations, 11 alag ideas. Ek bhi pass nahi hua.**

Gate failure counts: deflated Sharpe **9/9**, drawdown **9/9**, walk-forward efficiency
**9/9**, beats-baseline **9/9**, random-entry control **8/9**.

---

## 5. Chaar cheezein jo naapne se maloom huyin (aur jo bot banane se pehle bachani thin)

**F5 — Gold ke macro drivers explainers hain, predictors nahi.** Real yields aur dollar ka
gold se same-date correlation **−0.33** hai; sirf published data use karo to **−0.03**. Jo
koi bhi ise same-date data par backtest karega usay shandar natija milega jo hasil karna
na-mumkin hai.

**F7 — Triple-swap-night se bachna kaam nahi karta.** Naive arithmetic ne +1.01%/saal ka
wada kiya, measurement ne **−1.16%** diya. Wajah: flat rehne se us din ka expected return
bhi chhoot jata hai.

**F9 — Owner ki 10% drawdown limit hi asal constraint hai.** Baseline khud 10% vol target
par **24.36%** drawdown karta hai. Comply karne ke liye size 3–5% vol par lani parti hai,
aur us par return $128–171/saal reh jata hai. **Yeh strategy ka aib nahi — yeh us risk
budget ki qeemat hai.**

**F11 — Futures is account size par istemal hi nahi ho sakte.** Ek MGC micro contract $10,000
par **12.8× bara** hai. Woh $65,000–128,000 par sensible banta hai. Maine `COSTS.md` ka
venue switch trigger amend kiya, kyunke woh sirf carry dekhta tha aur yeh check karta hi nahi
tha ke naya venue position express kar sakta hai ya nahi.

---

## 6. Jahan main ghalat tha (record par, kyunke predictions log mein thin)

| Prediction | Natija |
|---|---|
| A1a "baseline ke qareeb rahegi, us se upar nahi" | ✅ sahi — +0.420 vs +0.502 |
| P4 ensemble "real but small improvement, gauntlet clear nahi karegi" | ✅ sahi |
| P4 "correlations 0.6–0.85 hongi" | ❌ **ghalat** — 0.484 nikleen |
| P4b "silver correlation 0.55–0.75" | ✅ sahi — 0.618 |
| P4b "Calmar 10–25% behtar hoga" | ❌ **ghalat** — **−32%** hua |
| F9 "futures financing ka masla hal karenge" | ❌ **ghalat** — F11 mein khud tasheeh ki |

P4b ki ghalti ki wajah: maine silver ki apni standalone quality check kiye baghair maan
liya ke woh gold jaisi hogi. Woh +0.190 hai, gold +0.438.

---

## 7. Ab kya bacha — teen imandar raaste

**1. Order flow (P5).** Ekloti cheez jo **naya information** laati hai. Baqi sab wahi OHLCV
hai jo har retail trader ke paas hai — aur us par 26 combinations fail ho chuke. Databento ka
$100–125 free credit, CME gold futures ka MBO data 2010 se. **Yeh agla kaam hai.**

**2. Chhota number qabool karo.** $151/saal per $10,000 — magar yaad rahe woh number kisi
validated edge se nahi aaya.

**3. Ruk jao.** Yeh legitimate jawab hai aur ab tak iski qeemat **$0** rahi hai. Phase 9
(live) mein yeh maloom karna hazaar guna mehnga hota.

**Jo main nahi karunga:** risk limit barhana taake number achha lage. Woh owner ka faisla
hai, mera nahi — aur agar woh badle to natije usi hisab se dobara naape jayenge, us se
pehle nahi.

---

## 8. Abhi pending

| Kaam | Halat |
|---|---|
| Live spread distribution (session-wise) | Sampler chal raha hai, Mon 16:58 UTC tak. Market abhi band thi |
| Slippage | Real fills chahiye — abhi assumption hai |
| Order flow feasibility (P5) | Agla kaam |
