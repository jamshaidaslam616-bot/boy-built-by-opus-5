# FINDINGS.md — jo naapne se mila, tarteeb-waar

Har entry: **kya naapa**, **natija**, aur **plan par kya asar**. Sirf measured cheezein —
raay alag se aur label ke saath.

---

## F1 (2026-08-08, P0) — Commission measured, aur shape ghalat thi

**Naapa:** account ki apni deal history se, 598 real XAUUSD fills.

| | Measured |
|---|---|
| On open | **$11.00 per lot** (598 fills, har ek bilkul yehi) |
| On close | **$0.00** |
| Round turn | **$11.00/lot = 0.253 bp** |

**Asar:** purana `$5.50 per side` assumption round-turn par **theek wohi $11.00** deta tha,
to koi backtest result nahi badla. Lekin woh ittefaq tha. Asal shape yeh hai ke commission
**poori open par** lagti hai — gold aur BTCUSD dono par confirmed.

**Iska ek natija hai jo strategy design badalta hai:** commission ka bojh **hold ke arse se
ulta** hai. Do minute ki trade aur do hafte ki trade dono $11/lot deti hain. Yeh M15/scalping
family ke against ek aur number hai aur daily-hold family ke haq mein.

**Aur ek sabaq:** yeh number account mein pehle se mojood tha. Owner se poochne ya nayi trade
bhejne ki zaroorat hi nahi thi. **History pehle parho, ijazat baad mein maango.**

---

## F2 (2026-08-08, P1) — Financing return ka 60%+ kha jaati hai

**Naapa:** XAUUSD D1, 12.6 saal (2014-01-14 → 2026-08-07), buy-and-hold, costs ke saath aur baghair.

Gold khud **+249%** chala ($1,243 → $4,342). Us par:

| | Bina financing | Is CFD account par |
|---|---|---|
| Return/yr | +8.77% | **+2.79%** |
| Sharpe | +0.643 | **+0.260** |

**Asar:** −5.66%/saal carry ne 12.6 saal par taqreeban aadha safar kha liya. Yeh strategy ka
masla nahi, **venue** ka hai — aur `COSTS.md` §6 ka switch trigger isi ke liye pehle se likha
gaya tha.

---

## F3 (2026-08-08, P1) — Is broker par *bahar rehna* khud qeemti hai

**Naapa:** 200-day trend overlay vs buy-and-hold, carry ke saath aur baghair.

| | Bina carry | Carry ke saath | Nuqsan |
|---|---|---|---|
| Buy and hold (vol-targeted) | 0.701 | 0.277 | −0.424 |
| 200d trend overlay | 0.814 | **0.502** | **−0.312** |

**Asar:** overlay ~30–40% waqt flat rehta hai aur us dauran carry nahi bharta. Uske faide ka
**aadha hissa signal se nahi, kiraya bachane se** aata hai.

**Yeh P3 mein alag report hoga**, warna woh signal ki kaamyabi lagega jabke woh broker ke
rate card ka natija hai. Futures par yeh faida nahi hoga.

---

## F4 (2026-08-08, P1) — D1 par teen guna zyada saaf data hai

**Naapa:** quality gate, har timeframe par coverage-by-year.

| Series | Archive ka dawa | **Usable window** | Zero-spread bars |
|---|---|---|---|
| XAUUSD **D1** | 2014→ | **2014–2026 (12.6 saal, 100% coverage)** | 32.17% |
| XAUUSD H4 | 2014→ | 2017–2026 | 14.44% |
| XAUUSD H1 | 2014→ | 2017–2026 | 10.38% |
| XAUUSD M15 | 2022→ | 2022–2026 (4.2 saal) | 15.10% |
| XAGUSD D1 | 2014→ | 2014–2026 (12.6 saal) | 33.33% |

H1/H4 ka archive 2014 se hone ka dawa karta hai magar 2014–16 mein sirf **5%** (H1) aur
**19%** (H4) bars hain — woh daily series hai H1/H4 ka label pehne hue.

**Asar:** A1 (daily trend) ko independently sab se behtar-supported candidate banata hai.
Aur **32% D1 bars par spread ZERO hai**, to per-bar archive spread kabhi use nahi hoga —
ek flat conservative bp assumption use hoti hai.

---

## F5 (2026-08-08, P2) — Gold ke macro drivers **explainers** hain, **predictors** nahi

**Naapa:** gold ke daily returns vs 10y TIPS real yield aur Broad Dollar Index, do tarah se —
ek same observation date par, doosra sirf us data par jo us waqt **publish** ho chuka tha.

| Driver | TRUE (same date) | USABLE (as published) | n |
|---|---|---|---|
| 10y real yield (`DFII10`) | **−0.3254** | −0.0250 | 3,137 / 2,211 |
| Broad dollar (`DTWEXBGS`) | **−0.3335** | +0.0345 | 3,115 / 2,450 |

**TRUE column data ki sehat sabit karta hai** — dono woh strong negative relationship dikhate
hain jo literature kehti hai. Yaani pipeline theek hai.

**USABLE column poora rishta gayab kar deta hai.** −0.33 se −0.03.

**Aur yeh sirf publication lag ki wajah se nahi hai** — yeh us se zyada bunyadi baat hai.
Same-day co-movement **kabhi** tradeable nahi hoti: aaj ka yield move jaanne ke liye aaj ka
din khatam hona parta hai. Lag chahe 1 din ho ya 10, jawab wohi rehta hai.

**Asar on the plan — B1/B2 ki tareef badalti hai:**

- **Change-triggers ke taur par B1/B2 mar chuke.** "Real yield gira → gold khareedo" ka koi
  tradeable version nahi hai. Yeh P3 mein test hone se **pehle** maloom ho gaya, jo hafton
  bachata hai.
- **Level-based slow regime filters ke taur par woh abhi zinda hain.** "Pichli tirmahi mein
  real yields gir rahi hain" ek aisi **state** hai jo 4-din ke lag se nahi marti, kyunke woh
  hafton par harkat karti hai. P3 sirf yeh version test karega.

**General sabaq, kyunke yeh dobara laagu hoga:** ek documented, strong, real correlation ka
tradeable hona zaroori nahi. Jo koi bhi "gold vs real yields" ko same-date data par backtest
karega usay shandar natija milega jo hasil karna na-mumkin hai.

---

## F6 (2026-08-09, P2) — COT ka contrarian dawa support nahi hota; sign ULTA hai

**Naapa:** CFTC COT gold (088691), 709 weekly reports 2013–2026, managed money positioning
ka 3-saal COT index, aur uske baad ke 1/4/13-week gold returns. Sirf **as published** data
(report Tuesday ka, release Friday 15:30 ET → 5-din lag).

**Pehli baat — linear correlation taqreeban zero:**

| Measure | On report date | As published |
|---|---|---|
| Managed money net (% OI) | −0.0199 | −0.0192 |
| Managed money COT index | −0.0021 | +0.0280 |
| Producer net (% OI) | +0.0459 | +0.0477 |

Yahan F5 ke barkhilaf **dono column barabar hain** — publication lag kuch nahi tor raha,
kyunke torne ko kuch tha hi nahi.

**Doosri baat — extremes par bhi dawa poora nahi hota, aur sign ulta hai.** Contrarian theory
kehti hai crowded longs ke baad **kamzori** aati hai. Measured (forward 4-week):

| Positioning bucket | mean % | naive t | **NW t** | **effective n** |
|---|---|---|---|---|
| 0.0–0.1 (max short) | +0.42 | +0.75 | +0.66 | 21 |
| 0.7–0.9 | +1.70 | +4.77 | **+3.48** | 83 |
| 0.9–1.0 (max long) | +1.83 | +3.52 | **+2.33** | 23 |

Spread (max short − max long) teeno horizons par **negative** = theory ke **ulta**.

**Meri methodological ghalti jo pakri gayi:** 13-week forward returns weekly data par
**12-week overlapping** hain. Pehla run naive t-stats de raha tha — 0.7–0.9 bucket par
**t=+10.53**. Newey-West correction ke baad woh **+3.86** hai aur effective n **150 se ghat
kar 20** ho jata hai. Yaani naive t ~2.7× phoola hua tha. Ab har jagah NW t report hota hai.

**Teesri baat — jo bacha woh momentum hai, contrarian nahi, aur trend se confounded hai.**
2013–2026 gold ka bara bull market tha aur managed money trend-followers hain, to "specs long"
aur "uptrend" taqreeban ek hi baat hai. Control:

| Trend | Positioning | n | mean % | NW t |
|---|---|---|---|---|
| UPTREND | crowded long | 197 | +1.86 | +4.08 |
| UPTREND | not crowded | 165 | +0.68 | +1.38 |
| DOWNTREND | crowded long | **13** | −0.21 | −0.13 |
| DOWNTREND | not crowded | 123 | +0.52 | +1.06 |

Uptrend ke andar gap +1.17% hai — yaani COT shayad trend ke upar kuch kehta hai. Lekin
downtrend/crowded cell mein sirf **13 observations** hain, jo kuch nahi hai.

**Asar on the plan:** B7 (COT) **contrarian signal ke taur par register nahi hoga** — jo
literature kehti hai woh is data par nahi milta. Agar register hoga to **momentum-confirmation
overlay** ke taur par, aur us ka prior kamzor hai kyunke sample chhota hai aur ek hi bull
market hai.

**Yeh sab exploratory hai.** 19 cells dekhe gaye, aur woh `reports/prereg.jsonl` ki pehli
entry mein **trial count ke taur par darj** hain — taake har baad wali hypothesis ka Deflated
Sharpe bar pehle se ooncha ho.

---

## F7 (2026-08-09, P2) — Triple-swap night se bachna **kaam nahi karta**

**Naapa:** is broker par triple swap **Wednesday** hai. Kya us raat flat reh kar paisa bachta hai?

**Naive arithmetic ne kaha haan:**

| | bp of notional |
|---|---|
| Normal night financing | 1.206 |
| Triple night, **extra** charge | 2.413 |
| Round trip to get flat | 0.470 |
| **Gross saving per week** | **+1.943** |
| **Annualised** | **+1.010%** |

**Measurement ne kaha nahi:**

| | Return/yr | Sharpe | Turnover |
|---|---|---|---|
| Hold through | +4.05% | **+0.502** | 7/yr |
| Flat over triple night | +2.89% | **+0.403** | 47/yr |

**Farq: −1.16% return, −0.099 Sharpe.**

**Kyun naive arithmetic ghalat thi:** usne carry saving ko round-trip cost se compare kiya
aur **us din ka expected return bhool gayi**. Ek positive-expectation position ke liye koi bhi
din chhorna us din ka return bhi chhorna hai. Aur turnover 7 se **47/yr** ho gaya.

**Control confirm karta hai carry saving asli hai:** financing off karke difference −0.125
Sharpe hai, financing on karke −0.099. Yaani saving ne +0.026 Sharpe diya — **real, magar us
se bohot chhota jo woh kharch karti hai.**

**Sabaq:** "free money" wali carry optimisation naapne par mar gayi. Yeh 20 minute mein pata
chala, bot mein build hone ke baad nahi.

---

## F8 (2026-08-09, P3) — Gauntlet ka verdict: **kuch bhi pass nahi hua**

**Naapa:** 9 pre-registered hypotheses, 20 parameter combinations, sab **register hone ke
baad** chalayin. Deflation 42 trials par (P2 ki 19 exploratory cells + 3 baseline + 20 ab).

| Candidate | Best Sharpe | Control z | DSR | Verdict |
|---|---|---|---|---|
| A1b MA crossover (50/200) | **+0.423** | +1.78 | 0.1357 | FAIL |
| A1a momentum (lookback 50) | +0.420 | +2.15 | 0.1334 | FAIL |
| A1c confidence trend | +0.361 | +1.62 | 0.0904 | FAIL |
| A1×B2 dollar-gated trend | +0.326 | +1.64 | 0.0704 | FAIL |
| A1×B1 yield-gated trend | +0.295 | +1.48 | 0.0558 | FAIL |
| B2 dollar regime | +0.104 | +1.28 | 0.0098 | FAIL |
| A10 vol breakout | +0.081 | +1.06 | 0.0078 | FAIL |
| B1 real yield regime | +0.004 | +0.78 | 0.0033 | FAIL |
| **B3 gold–silver reversion** | **−0.688** | −1.70 | 0.0000 | FAIL |

Gate failures: deflated Sharpe **9/9**, max drawdown **9/9**, walk-forward efficiency **9/9**,
beats-baseline **9/9**, random-entry control **8/9**.

**Teen baatein jo isme se nikalti hain:**

**(a) Ek bhi candidate baseline (+0.502) ko beat nahi kar saka.** Behtareen +0.423 tha.
Meri registered prediction A1a ke liye yehi thi — *"baseline khud ek trend rule hai, to yeh
zyadatar apne aap se muqabla kar raha hai"* — aur woh log mein test se **pehle** darj hai.

**(b) Long/short versions long/flat baseline se BURI hain.** Baseline downtrend mein flat ho
jata hai; candidates short ho jate hain. Gold is arse mein +249% chala, to short side ne paisa
khaya. **Lekin yeh 12-saal ke ek bull market ka in-sample observation hai** — "gold short mat
karo" is bunyad par kehna theek wohi curve-fitting hai jis se bachne ke liye yeh lab bani hai.
Isay finding ke taur par darj kar raha hoon, rule ke taur par nahi.

**(c) B3 (gold–silver) sirf fail nahi, tabah hua** — Sharpe −0.688, **75% drawdown**. Carry ka
sawal uthne se pehle hi mar gaya: is arse mein ratio mean-revert nahi kiya, trend kiya.
Insaaf ki baat: meri implementation mein **stop nahi tha** (|z| < 0.5 tak hold), to yeh us
specification ki maut hai, poore idea ki nahi. Stop wala version ek **nayi hypothesis** hoga
aur usay alag register karna paregi.

---

## F9 (2026-08-09, P3) — Sab se ahem number: **owner ki limit par yeh ~$128–171/saal deta hai**

**Yeh P3 ne ek aisi cheez khol di jo maine notice nahi ki thi: baseline khud gauntlet ka
drawdown gate fail karta hai.** BASELINE.md 10% vol target par 24.36% max drawdown report
karta hai — owner ki 10% live limit se do guna zyada. Yaani Sharpe ka bar us strategy ne set
kiya jo risk par reject ho jati.

Gate badalna ghalat hai — woh owner ka hai. **Size badalni hai.** Naapa:

| Vol target | Return/yr | Max DD | $ on $10,000 | Verdict |
|---|---|---|---|---|
| 10% | +4.05% | 24.36% | +$405 | breaches both |
| 6% | +2.50% | 15.23% | +$250 | breaches both |
| 5% | +2.10% | 12.82% | +$210 | passes backtest, breaches live |
| 4% | +1.69% | 10.36% | +$169 | passes backtest, breaches live |
| **3%** | **+1.28%** | **7.85%** | **+$128** | **OK — inside live limit** |

MA 50/200 (long/short) 4% par comply karta hai: **+1.71%/saal = +$171**.

**Yeh strategy ka aib nahi.** Yeh us cheez ki qeemat hai: gold trend-following, 10% drawdown
tolerance par, ek aise venue par jo long rakhne ka 5.66%/saal leta hai. Financing akela
**+6.90% gross ko +4.05% net** kar deti hai — **gross ka 41%**.

**Teen imandar raaste, aur inmein "limit dheeli karo" shamil nahi:**

1. **Chhota number qabool karo.** $10,000 par is risk budget ki yehi qeemat hai, aur woh
   compound hoti hai.
2. **Venue theek karo.** Financing gross ka 41% le jaati hai. Futures yeh charge karte hi
   nahi — `COSTS.md` §6 ka switch trigger.
3. **Behtar signal dhoondo.** P3 mein sab fail hua, to iska matlab **naya information**
   (order flow), naye parameters nahi.

**Limit wahin rahegi jahan owner ne rakhi hai. Main usay kisi number ko behtar dikhane ke
liye nahi barhaunga — is number ke liye bhi nahi.**

---

## F10 (2026-08-09, P4) — Multi-speed ensemble: asli behtari, magar chhoti

**Naapa:** 5 trend speeds (20/50/100/200/400), pehle correlation, phir ensemble. Registered
before testing.

**Correlations mere andaze se kam nikleen — yaani speeds zyada alag hain:**

mean pairwise **0.484** (range 0.258–0.650). Maine register karte waqt **0.6–0.85** predict
kiya tha. **Yeh prediction ghalat thi**, aur achhi taraf se ghalat.

| | Sharpe | Max DD | Calmar |
|---|---|---|---|
| Best single speed (trend_50) | +0.420 | 26.86% | 0.149 |
| **Ensemble, long-only** | **+0.438** | **17.59%** | **0.166** |

Calmar **+11.5%** behtar. Aur us number par jo asal mein matter karta hai:

| | Compliant size | Return | **$10,000 par** |
|---|---|---|---|
| Baseline (200d overlay) | 3% vol | +1.28% | **$128** |
| **Ensemble, long-only** | **5% vol** | **+1.51%** | **$151** |

**+18% us number par jo matter karta hai.** Lekin gauntlet phir bhi FAIL — DSR 0.1445,
control z +1.32, drawdown 17.59% (limit 15%), aur baseline Sharpe (+0.502) se neeche.

**Meri registered prediction:** *"real but small improvement... not enough to clear the
deflated Sharpe bar after 44 trials"* — **yeh theek nikli**, sivaye correlation ke andaze ke.

---

## F11 (2026-08-09, P5) — Venue verdict **ULTA** ho gaya: futures is account par na-mumkin hain

**Yeh meri apni F9 wali baat ki tasheeh hai.** F9 mein maine likha ke financing gross ka 41%
leti hai aur futures uska hal hain. **41% measured aur durust hai. Natija ghalat tha.**

**Do ghaltiyan thin:**

**(a) Us −5.66% ka zyada hissa broker ka charge nahi, asli carry hai.** Koi bhi leveraged long
gold position kahin bhi interest deti hai. Gold futures wohi carry apne basis mein rakhte hain
— long futures roll ke zariye wohi deta hai. Broker ka **markup** shayad 1.5–1.7pp hai, poora
5.66 nahi. Aur jahan broker waqai kuch leta hai woh **short side** hai, jahan woh 0.00% deta
hai jabke short futures poora credit kamati hai.

Chunke P4 ki behtareen strategy **long-only** nikli, venue switch usi side par sab se **kam**
faida deta hai.

**(b) Aur yeh decisive hai — futures ko itna chhota kiya hi nahi ja sakta.**

Gold ki measured annual volatility **14.8%**:

| Instrument | Size | Notional | Annual vol | $10k par 5% target ke liye chahiye | Oversized |
|---|---|---|---|---|---|
| MGC micro futures | 10 oz | $43,423 | $6,421 | **0.078 contracts** | **12.8×** |
| GC full futures | 100 oz | $434,231 | $64,212 | 0.008 | 128.4× |
| **CFD minimum** | **1 oz** | **$4,342** | **$642** | **0.779** | — |

Ek MGC contract maqool position tab banta hai jab capital **~$64,000** (10% vol) ya
**~$128,000** (5% vol) ho.

**Faisla: CFD par raho.** Iski financing achhi nahi — magar $10,000 par futures carry ke
faide ke bawajood na-qabil-e-istemal hain. CFD ka 0.01-lot minimum MGC se **10× barik** hai,
aur wahi ek wajah hai ke yeh strategy is size par implement ho sakti hai.

**`COSTS.md` §6 ka switch trigger amend kar diya gaya hai** — woh sirf carry dekhta tha aur
kabhi check nahi karta tha ke naya venue position express kar sakta hai ya nahi. Ab dono
shart hain. Trigger chup chaap chhorne ke bajaye theek kiya, kyunke woh jaise tha waise fire
ho kar hamein aise venue par le jata jahan trade karna hi mumkin nahi.

**Ek aur baat jo isi hisab se nikli:** CFD ka apna 0.01-lot minimum bhi 5% vol target par
**1.28× bara** hai (0.779 chahiye, 1 minimum). Yaani chhote se chhoti compliant position bhi
~6.4% vol par chalegi, 5% par nahi. Yeh $10,000 account ki hadd hai, kisi bug ki nahi.

---

## F12 (2026-08-09, P5) — Behtar volatility forecast **convert nahi hota**

Yeh direction predict karne ki koshish nahi thi. F9 ne dikhaya binding constraint **drawdown**
hai, to yeh us par seedha waar tha: agar volatility behtar forecast ho to sizing zyada durust
hogi, drawdown surprises kam hongi, aur **usi 10% limit par bari position** chal sakegi.

**Forecast accuracy waqai behtar hui — 3 guna:**

| Model | OOS R² | RMSE |
|---|---|---|
| Rolling 60d (incumbent) | 0.065 | 0.0657 |
| **HAR (daily/weekly/monthly)** | **0.206** | 0.0609 |

Bilkul jaise literature kehti hai. (GVZ add nahi ho saka — FRED us waqt rate-limit kar raha
tha. Woh baad mein dobara try hoga.)

**Magar woh natije mein tabdeel nahi hua:**

| Forecast | Compliant target | Return/yr | maxDD | **$10,000 par** |
|---|---|---|---|---|
| Rolling 60d | 5% | +1.51% | 9.04% | **$151** |
| HAR | 4% | +1.08% | 8.16% | **$112** |

**Wajah, naapi gayi:**

| | mean | **std** | avg exposure |
|---|---|---|---|
| Rolling 60d | 0.137 | **0.054** | 0.254 |
| HAR | 0.134 | **0.031** | 0.199 |

HAR ka forecast **zyada smooth** hai. Iska matlab `target / forecast` kam variable hai, yaani
low-vol daur mein woh utna size up nahi karta. Rolling 60d ne un daur mein bari position li,
aur is bull market mein woh faidemand nikla.

**Lekin is bunyad par rolling 60d ko "behtar" declare karna khud wohi ghalti hogi jis se
bachne ke liye yeh lab bani hai.** Woh faida ek hi 12-saal ke raaste ka in-sample outcome hai.
Dono ke darmiyan farq established nahi hai.

**Imandar natija:** volatility 3× behtar forecast ho sakti hai, aur **is strategy par woh
behtar natija nahi deti**. Meri registered prediction ne mechanism theek pakra tha —
*"drawdown sustained adverse trends se aata hai utna hi jitna volatility surprises se, aur
behtar sizing pehle wale mein madad nahi kar sakti"* — magar maine 5–15% behtari predict ki
thi, aur **degradation mila**.

**Yeh 6 mein se teesri prediction hai jo ghalat nikli.** Woh sab log mein test se pehle darj
thin, isi liye ginni ja sakti hain.

---

## F13 (2026-08-10, P6) — Ek backtest path drawdown ko **1.58× kam** dikhata hai

Owner ne 10% drawdown limit barhane ki ijazat di aur number mujh par chhora. Andaze se
number chunna bekaar hota, to usay naapa: **5,000 block-bootstrap paths** (blocks ~21 din,
taake trend persistence bachi rahe jo drawdown banati hai).

| Vol target | Observed DD | median | p90 | **p95** | p99 | **p95 / observed** |
|---|---|---|---|---|---|---|
| 5% | 9.04% | 8.61% | 12.99% | **14.69%** | 18.30% | **1.63×** |
| 8% | 14.23% | 13.54% | 20.20% | **22.74%** | 27.86% | **1.60×** |
| 10% | 17.59% | 16.73% | 24.79% | **27.76%** | 33.85% | **1.58×** |
| 15% | 25.62% | 24.36% | 35.28% | **39.19%** | 46.87% | **1.53×** |

**Ek 12.6-saal ka backtest path ek draw hai, poori tasveer nahi.** Us par limit set karo to
woh taqreeban **aadhi mumkin tareekhon** mein toot jayegi.

### Isne mere apne design ki ek incoherence pakri

Purana jodda: **backtest gate 15%, live halt 10%**. Woh be-maani tha — 15% observed par pass
hone wali strategy ka p95 live drawdown **~23.7%** hota, yaani us halt se do guna zyada jise
respect karna tha.

Sahi rishta yeh hai:

```
backtest gate  =  live halt / 1.58
```

Naya jodda: **live halt 20%, backtest gate 12.5%.** Ghaur karein yeh gate ko **sakht** karta
hai (15.0 → 12.5), dheela nahi. Natije dekhne ke baad threshold badalna sirf isliye jaiz hai
ke yeh **har candidate ke khilaf** jata hai, kisi ke haq mein nahi — P3, P4, P4b ka koi verdict
nahi badla, kyunke sab pehle hi 15% par fail thay (behtareen 17.59%).

### Limit kya khareedti hai — measured

Har limit par size aisi ke **p95** drawdown uske andar rahe:

| Live limit | Vol target | p95 DD | Return/yr | **$10,000 par** | p95 loss |
|---|---|---|---|---|---|
| 10% | 3.0% | 8.71% | +0.92% | **$92** | −$871 |
| 15% | 5.0% | 14.20% | +1.51% | **$151** | −$1,420 |
| **20%** | **7.0%** | **19.50%** | **+2.09%** | **$209** | **−$1,950** |
| 25% | 9.0% | 24.54% | +2.65% | $265 | −$2,454 |
| 30% | 11.0% | 29.38% | +3.19% | $319 | −$2,938 |

**Faisla: 20%.**

- **10% par nahi** — wahan koi trade karne layak size fit hi nahi hoti, to halt normal
  variation par fire hoti aur ek theek chalte system ko rok deti.
- **30% par nahi** — wahan halt kabhi fire hi nahi hogi, yaani woh control nahi rahegi,
  sajawat ban jayegi. Aur 20% se 30% jaane par +$110/saal ke liye p95 loss $1,950 se
  **$2,938** ho jata hai — bura sauda.
- **20% par** halt ek asli signal rehti hai ke kuch ghalat hai, aur p95 uske andar gunjaish
  ke saath baith jata hai.

### Magar — aur yeh number se zyada ahem hai

Is strategy ka control z-score **+1.32** hai aur Deflated Sharpe **0.14**. Woh apne hi
rotation se **statistically alag nahi** hai. **Koi validated edge nahi hai.**

Limit barhana us haqeeqat ke **dono** taraf ko barhata hai. Edge asli hua to return usi
nisbat se barhega; nahi hua to nuqsan usi nisbat se barhega aur drawdowns waise bhi aayenge.

**Number ko chhota rakhne wali cheez limit nahi thi — sabit-shuda edge ki ghair-maujoodgi
hai.** Limit barhana durust **tayyari** hai; woh natija nahi hai. Main isay kisi bhi size
par deploy nahi karunga jab tak koi cheez gauntlet pass na kare.

---

## F14 (2026-08-10, P5b) — Open interest, aur ek control jo maine khud kharab bana liya tha

Free mein **asli futures volume nahi milta** — Stooq automated requests refuse karta hai, aur
Yahoo ke GC=F ka median volume **232 contracts/din** hai jabke asli ~250,000 hai (continuous-
contract artifact). To akhri free non-price input **open interest** tha, jo COT files mein
pehle se maujood tha aur test nahi hua tha.

### Classic four-quadrant dawa support nahi hota

| Price | Open interest | n | Forward 4-week % |
|---|---|---|---|
| rising | rising ("naya paisa") | 193 | +0.78 |
| rising | falling ("short covering") | 165 | +0.82 |
| falling | rising | 149 | +0.62 |
| falling | falling | 145 | **+1.05** |

Charon quadrant taqreeban barabar. Textbook jise sab se mazboot kehti hai (rising/rising) woh
**doosre number par bhi nahi**.

### Strategy test — registered hypothesis ULTA fail hui

| Variant | Compliant size | **$10,000 par** |
|---|---|---|
| Ungated trend (P4 best) | 7% | **$209** |
| **Rising-OI gate** (registered dawa) | 10% | **−$29** |
| Falling-OI gate | 8% | $248 |

Registered hypothesis **−113.7%** par fail. Aur "falling OI" ulta natija hai — post-hoc flip,
jise finding kehna cheating hoga.

### Aur yahan maine taqreeban ek jhoota signal accept kar liya tha

"Falling OI" $248 vs ungated $209 dekh kar maine control chalaya — magar **ghalat control**:
random **per-bar** gates. Woh position ko har bar chop karte hain (bhaari turnover), jabke OI
gate haftay bhar tika rehta hai. Yaani main ek persistent gate ka muqabla ek high-turnover
random gate se kar raha tha.

Sahi control woh hai jo **gate ko rotate** kare — duty cycle, persistence, weekly blockiness
sab barqarar, sirf alignment tabah. Farq:

| Control | Real | Control mean ± sd | **z** |
|---|---|---|---|
| Random per-bar gates (**kharab**) | $248 | $144 ± 33 | **+3.2** |
| **Rotated gates (sahi)** | $248 | $184 ± 42 | **+1.55** |
| Rotated gates, carry off | $478 | $369 ± 62 | +1.75 |

**Kharab control ne z ko do guna phula diya tha.** +3.2 ek discovery lagta hai; +1.55 wohi
shor hai jo is project mein har jagah hai.

**Sabaq, aur yeh `control.py` ke design ka poora nuqta hai:** control ko strategy ke saath
**har us cheez par match** karna chahiye jo returns par asar daalti hai — turnover, holding
period, duty cycle, persistence — aur sirf market ke saath **alignment** tornी chahiye. Jo
control turnover par match nahi karta, woh turnover ka faida signal ke khaate mein daal deta
hai.

`circular_shift_controls` yeh theek karta hai aur woh pehle din se maujood tha. Maine ek jaldi
mein likha gaya check us ki jagah istemal kar liya. **Ab koi bhi control aisa nahi chalega jo
rotation na ho.**

---

## F15 (2026-08-10, P7–P10) — Poore project ka asal jawab: **edge itni chhoti hai ke yeh data usay sabit hi nahi kar sakta**

Owner ne approach revise karne ko kaha. Maine ek asli methodological ghalti pakri: **maine
strategies chuni aur test kin, jabke pehle naapna chahiye tha ke predictability kahan hai.**
Woh naapa, aur uske baad wahan banaya jahan usne isharah kiya.

### P7 — structure kahan hai (yeh sab se pehla kaam hona chahiye tha)

| TF | bars | Variance ratio | VR z | Continuation | t | vs costs |
|---|---|---|---|---|---|---|
| M15 | 99,999 | 0.960 | −0.95 | −0.049 bp | −0.64 | 0.11× |
| H1 | 55,683 | 0.984 | −1.49 | −0.381 bp | **−2.14** | 0.81× |
| **H4** | 15,094 | **1.034** | +0.67 | **+1.079 bp** | +1.64 | **2.30×** |
| D1 | 3,866 | **0.848** | −0.98 | −0.698 bp | −0.24 | 1.48× |

**Do cheezein jo meri ab tak ki har koshish ke khilaf thin:**

- **D1 ka VR 0.848 hai — daily gold halka sa REVERT karta hai, trend nahi.** Aur P3/P4 ki har
  strategy D1 par **trend** thi. Main ulti timeframe par ulta signal chala raha tha.
- **H4 ekloti jagah hai jahan VR > 1 aur effect costs se bara hai** — bilkul wahan jahan owner
  ke purane project ne independently isharah kiya tha aur main seedha D1 par chala gaya.

**Kisi bhi timeframe ka variance ratio significant nahi hai** (har |z| < 2).

### P8 aur P9 — jahan measurement ne kaha, wahan banaya. Phir bhi fail.

| Kya | Best Sharpe | Control z | Compliant $ |
|---|---|---|---|
| H4 trend (5 variants) | +0.297 | +1.54 | $139 |
| H4 trend + D1 filter (3) | +0.306 | +1.31 | $101 |
| **D1 mean reversion (6)** | **−0.168** | +0.18 | koi size nahi |
| **H1 extreme reversion (4)** | **−0.470** | −0.60 | koi size nahi |

Mean reversion sirf fail nahi hui, **bhaari nuqsan** mein gayi (−5% se −9%/saal). H1 ka
bucket analysis dikhata hai reversion move ke size ke saath **monotonic nahi** — 80–95th pct
bucket actually continuation hai. Yaani woh structure nahi, shor hai.

### Aur phir woh hisab jo sab kuch samjha deta hai

Ek edge ko **sabit** karne ke liye kitna data chahiye? `t = Sharpe × √years`, aur 95%
confidence ke liye `t ≥ 2`:

| Sharpe | Saal chahiye | Gold D1 par maujood | Sabit ho sakti? |
|---|---|---|---|
| 0.30 | 44.4 | 12.6 | **NAHI** |
| **0.44** | **20.9** | **12.6** | **NAHI** |
| 0.60 | 11.1 | 12.6 | haan |
| 1.00 | 4.0 | 12.6 | haan |

**Behtareen measured strategy ka Sharpe +0.438 hai. Usay sabit karne ke liye 20.9 saal
chahiye. Hamare paas 12.6 hain.**

Aur ab yeh dekhein: 12.6 saal par us Sharpe ka **tawaqqo shuda** t **+1.55** hai. Maine jo
control z naapa woh **+1.32** tha.

**Yeh dono numbers match karte hain.**

### Iska matlab kya hai — aur yeh "koi edge nahi" se alag baat hai

Mere saare FAIL verdicts do mein se kisi bhi soorat ke saath consistent hain:

1. **Koi edge hai hi nahi**, ya
2. **~0.44 ki edge maujood hai aur yeh dataset usay sabit karne ke liye chhota hai**

**Main in dono mein farq nahi kar sakta. Is data se koi nahi kar sakta.** Yeh gold ki 12.6
saal ki tareekh ki hadd hai, meri koshish ki nahi.

### Nikalne ka raasta waqt nahi — **cross-section** hai

Ek market par Sharpe 0.44 mila. Yeh **theek wohi number hai jo literature single-market trend
following ke liye batati hai**. Woh nakami nahi — woh confirmation hai. Trend-following funds
Sharpe 0.8–1.0 isliye paate hain ke woh **50–100 markets** trade karte hain, ek nahi:

| Markets | Portfolio Sharpe | Sabit karne ko saal |
|---|---|---|
| 1 | 0.44 | **20.9** |
| 5 | 0.77 | 6.7 |
| **10** | **0.90** | **4.9** |
| 20 | 1.00 | **4.0** |

*(avg pairwise correlation 0.15 farz ki, jo asset classes ke darmiyan normal hai)*

**Yaani: behtar gold strategy dhoondna ghalat sawal tha. Sahi sawal zyada markets hai.**
Wahi code, wahi lab, wahi $10,000 — 20–30 instruments par. Exness par woh sab maujood hain.

Yeh **gold bot** ke original brief se scope change hai, isliye main isay naap kar pesh kar
raha hoon, khud apna kar nahi.

---

## F16 (2026-08-10, P12) — Multi-market test, aur **F15 ki apni reasoning ghalat nikli**

Owner ne kaha "profit chahiye, jahan se bhi aaye" — to maine 20 instruments ka data laaya
(FX majors, metals, energy, indices, crypto) aur **wahi rule sab par** chalaya.

### Pehle ek asli bug jo pakra gaya

Pehle run mein carry **~10,000× kam** parh rahi thi — gold −0.001% dikha raha tha jabke uska
measured −5.68% hai. Formula mein `point_value_per_lot` chhoot gaya tha. Yeh bug natije ko
**khushnuma taraf** jhuka raha tha, isliye ahem tha. Theek karke sanity check lagaya: ab gold
−5.68% parhta hai measured −5.66% ke against.

### Aur us bug ke theek hone se sab se bara structural fact nikla

| Symbol | Long %/yr | Short %/yr |
|---|---|---|
| XAUUSD | −5.68 | 0.00 |
| XAGUSD | −5.76 | 0.00 |
| BTCUSD | −9.28 | 0.00 |
| US500 | −8.76 | 0.00 |
| EURUSD | −2.40 | 0.00 |
| USDCHF | 0.00 | **−5.74** |
| **USOIL** | 0.00 | **−31.38** |

**Yeh broker har instrument par kiraya leta hai, aur hamesha us taraf jahan aap khade hain.**
Gold par long mehnga hai; USDCHF par short; USOIL par short 31%/saal. Koi taraf muft nahi.

### Natija

| Basket | Markets | Correlation | **Mean single SR** | **Portfolio SR** | $10k par |
|---|---|---|---|---|---|
| WIDE (2020–2026) | 19 | +0.171 | **−0.201** | **−0.404** | **−$141** |
| LONG (2014–2026) | 12 | +0.192 | **−0.187** | **−0.316** | **−$89** |

**Portfolio paisa haarta hai.** Aur wajah saaf hai: trend system ko position **rakhni** parti
hai, aur yeh broker rakhne ka kiraya leta hai. Yeh do cheezein ek saath nahi chal sakteen.

### F15 ki meri reasoning kahan ghalat thi

F15 mein maine likha: *"Sharpe 0.44 wohi hai jo literature single-market trend ke liye kehti
hai, to 20 markets Sharpe 1.0 denge."* Us mein ek **na-kaha hua farz** tha: ke 0.44
**representative** hai.

**Woh representative nahi tha. Woh 19 draws ka MAXIMUM tha, aur us distribution ka mean
negative hai.**

Correlation ka mera andaza sahi nikla (predict 0.05–0.25, mila 0.171/0.192). **Mean Sharpe ka
farz ghalat tha, aur wahi poori daleel utha rahi thi.**

### Aur isse woh baat sabit hoti hai jo control pehle din se keh raha tha

Gold ka +0.438 **selection** tha — 19 markets par wahi rule chalao to koi na koi 0.4+ dikhayega,
jaise 19 sikke uchhalo to koi na koi lagataar heads laayega.

**Random-entry control ne yeh shuru se pakra hua tha: z = +1.32, kabhi significant nahi.** Main
poore project mein us ke ird-gird raaste dhoondta raha. Woh theek tha aur main ghalat.

### Jo ab yaqeeni taur par maloom hai

1. Yeh trend rule ka **markets ke aar-paar koi edge nahi** (mean Sharpe costs ke baad negative)
2. Gold ka nazar aane wala edge **selection** tha
3. **Is broker ki financing hi asal rukawat hai** — 2% se 31%/saal, har instrument, har taraf.
   Koi bhi strategy jo hafton position rakhe, yahan structurally nuqsan mein hai.

Point 3 poore project ki sab se qeemti maloomat hai, aur woh us se bilkul mukhtalif hai jo
maine F9 mein socha tha. Masla gold nahi tha. Masla **kiraya** hai.

---

## F17 (2026-08-10, P13–P14) — Owner ki tajweez ne sab se bara faida diya, aur phir bhi kaafi nahi

Owner ne do cheezein tajweez kin: **swap-free account** aur **day trading**. Dono jaiz thin
aur dono ne kaam kiya. Raaste mein maine apne teen bugs pakde.

### Bug 1 — carry ko rollover par charge karna chahiye, har bar par nahi

Swap raat mein **ek baar** lagta hai, server midnight par. Mera model annual rate ko **har
bar** par phaila raha tha. Hamesha-khuli position ke liye woh theek hai; intraday ke liye
**ghalat** — woh us strategy ko saza deta hai jo swap se bachne ke liye hi bani ho. Meri pehli
reading day-trading variant par 3.77%/saal swap charge kar rahi thi jo usne kabhi owe hi nahi
kiya.

### Bug 2 — bar length ka andaza pehle do bars se

Fix karte waqt maine bar length `index[1] - index[0]` se li. Asli series mein wahan **weekend
gap** hota hai, to H1 data 24-ghante ka lagta tha aur daily branch mein chala jata tha —
**6,240 raatein saal mein ginta tha 260 ke bajaye**. Us se +0.75% wali strategy **−22.64%**
dikhne lagi. Ab median gap use hota hai, aur uska permanent test hai.

### Bug 3 — returns ko rotate karna control nahi hai

P14 ka pehla control "rotations +0.142 ± **0.000**" de raha tha. Wajah: maine **returns**
rotate kiye. Sharpe = mean/std, aur rotation dono ko badalta hi nahi — to control aur strategy
hamesha barabar honge. Sahi control **positions** rotate karta hai, per instrument, phir book
dobara banata hai. **Yeh doosri baar hai** (F14 pehli) ke maine jaldi mein kharab control
likha; ab dono jagah `circular_shift_controls` hi chalta hai.

### Sahi model par, owner ki tajweezein — gold H1

| Variant | Sharpe | Return/yr |
|---|---|---|
| Abhi wala (swap charged) | +0.167 | +1.02% |
| **Swap-free** | **+0.320** | **+2.27%** |
| **Day trade (raat ko flat)** | **+0.274** | **+1.76%** |

**Dono ne Sharpe taqreeban do guna kiya.** Aur day trading ke haq mein ek aur baat: gold ka
move **intraday +10.11%/saal** hai aur **overnight sirf +2.08%** — yaani raat ko flat hone se
bohot kam chhutta hai aur poora swap bachta hai.

### 7-din free window, 19 markets par — owner ne bataya ke pehle 7 din free hain

| Scenario | Book Sharpe | Mean single | $10k par |
|---|---|---|---|
| A. slow trend, swap charged | −0.311 | −0.033 | **−$119** |
| B. slow trend, har 7 din roll *(unverified)* | −0.003 | +0.100 | −$9 |
| **C. fast trend, 7 din par capped** | **+0.142** | +0.032 | **+$62** |
| D. fast trend, no cap, swap charged | −0.155 | −0.108 | −$70 |

**Free window ki qeemat: +$180/saal.** Book pehli baar **positive** hui (−$119 → +$62). Yeh
poore project mein sab se bara single sudhaar hai, aur woh owner ki tajweez se aaya.

### Magar control phir bhi fail

Positions rotate kar ke, per instrument, book dobara bana kar:

    strategy +0.142   vs rotations −0.053 ± 0.386   **z = +0.50**  (chahiye +2.00)

Sharpe +0.142 ko sabit karne ke liye **199.7 saal** chahiye. 6.5 hain.

### Poore project ka pattern, ek jumle mein

**Har cost fix ne madad ki. Koi signal zinda nahi bacha.**

Costs ab taqreeban behtareen hain jo is account par mumkin hai — swap-free ke 7 din, intraday
hold, measured spread, measured commission. **Jo baqi hai woh signal hai, aur wahan 19 markets
par bhi kuch nahi mila.** Signal behtar karne ka matlab **naya information** hai (order flow),
naye parameters nahi.

---

## F18 (2026-08-14, P15–P16) — **$10,000 par jin markets mein signal hai, unhein size hi nahi kar sakte**

P15 ne cross-sectional momentum test kiya — pehla idea jo trend ka roop nahi tha. Natija
poore project ka behtareen tha: Sharpe **+0.395**, **+$247/saal**, 9 mein se 8 parameter
combinations positive. Control phir bhi fail (z = +0.56).

Phir production risk engine banate waqt woh cheez pakri gayi **jo P15 ne check hi nahi ki thi.**

### Backtest ek aisi book rakh raha tha jo maujood hi nahi ho sakti

14-leg book mein har leg ko risk ka chaudahwan hissa milta hai — $10,000 par taqreeban $700
notional per leg. Gold ki **sab se chhoti tradeable position $4,342** hai.

**Backtest gold ki 0.0016 lot rakh raha tha. Broker ka minimum 0.01 hai. Woh position 6 guna
chhoti thi us se jo mumkin hai.**

| Universe | Sharpe | $10,000 par |
|---|---|---|
| Saare 19 (P15 ne yeh report kiya) | +0.395 | **+$247** |
| **11 jo waqai trade ho sakte hain** | +0.026 | **−$2** |

**Poora $247 minimum lot size ignore karne ka artifact tha.**

### Aur wajah structural hai — yeh ittefaq nahi

Block huye: **XAUUSD, XAGUSD, XPDUSD, XPTUSD, USOIL, UKOIL, USTEC, BTCUSD** — yaani **saare
high-volatility markets**, bila istisna.

Mantiq: high volatility ka matlab hai ke risk target ke liye **kam notional** chahiye. Magar
broker ka minimum notional **fixed** hai. To jitna volatile instrument, utna hi uska minimum
uske risk share se bara.

| Instrument | Annual vol | Notional chahiye | Min notional | Natija |
|---|---|---|---|---|
| XAGUSD | 47.7% | $392 | $3,174 | 8× bara |
| USOIL | 54.1% | $346 | $779 | 2.3× bara |
| XAUUSD | 26.8% | $699 | $4,327 | 6× bara |
| EURUSD | 4.6% | $4,045 | $1,155 | OK |
| USDCAD | 3.8% | $4,871 | $1,000 | OK |

Jo 11 bache woh zyadatar **low-vol FX pairs** hain — aur meri apni per-market table ke mutabiq
**wahi markets thay jahan signal sab se kamzor tha** (EURUSD −0.20, USDCHF −0.35, USDCAD −0.33).

### Jawab, ek jumle mein

**Jin markets mein signal hai unhein $10,000 par size nahi kiya ja sakta. Jinhein size kiya ja
sakta hai unmein signal nahi hai.**

Yeh $10,000 account ki **structural** hadd hai — strategy ki nakami nahi, aur na hi kisi behtar
rule se hal hone wali. Wahi rukawat jo F11 mein futures ko le doobi thi, ab shipped strategy ko
le doobi hai. Farq sirf yeh hai ke is baar maine **build karte waqt** pakri, backtest ke bharose
rehne ke bajaye — aur ab uska permanent test hai
(`test_gold_cannot_be_a_leg_of_a_diversified_book_on_this_account`).

**Har woh number jo is check se pehle quote hua woh ek na-mumkin book naap raha tha.** Us mein
F-series ka +$247 shamil hai, jise yeh entry **theek karti hai, bachati nahi**.
