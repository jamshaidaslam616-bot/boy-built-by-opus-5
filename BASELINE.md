# BASELINE.md — the number to beat

**Established:** 2026-08-08, **before any candidate strategy existed**
**Data:** XAUUSD D1, 3,867 bars, 2014-01-14 .. 2026-08-07, Exness Zero demo
**Reproduce:** `.venv\Scripts\python.exe scripts\p1_baseline.py`

---

## Kyun yeh file sab se pehle likhi gayi

Sawal yeh nahi ke "bot ne paisa banaya ya nahi". Sawal yeh hai: **"bot us se behtar
hai jo bina bot ke ho sakta tha?"**

Yeh number **abhi** likha ja raha hai, kisi candidate ke banne se pehle — taake baad
mein aisa baseline na chun liya jaye jise koi candidate ittefaqan beat kar leta ho.

---

## 1. Natije

Sab 10% annual volatility par targeted, sab par wohi costs jo `COSTS.md` mein hain.

### Bina financing ke — yaani agar aap gold **rakhte** (CFD nahi)

| Baseline | Return/yr | Vol | **Sharpe** | Max DD |
|---|---|---|---|---|
| Buy and hold, unsized | +8.77% | 14.79% | +0.643 | 27.70% |
| Buy and hold, vol-targeted | +7.16% | 10.69% | +0.701 | 21.50% |
| 200d trend overlay, vol-targeted | +6.90% | 8.66% | **+0.814** | 20.20% |

### Is broker ki financing ke saath — yaani jo CFD account **asal mein** deta hai

| Baseline | Return/yr | Vol | **Sharpe** | Max DD |
|---|---|---|---|---|
| Buy and hold, unsized | +2.79% | 14.79% | +0.260 | 36.72% |
| Buy and hold, vol-targeted | +2.42% | 10.69% | +0.277 | 35.89% |
| **200d trend overlay, vol-targeted** | **+4.05%** | 8.65% | **+0.502** | 24.36% |

---

## 2. THE NUMBER TO BEAT — **Sharpe +0.502**

Koi bhi candidate strategy ko **out-of-sample par, wohi costs ke baad, +0.502 se
upar** hona parega. Yeh gauntlet ka `beats honest baseline` gate hai.

Yeh koi asaan bar nahi hai. 12.6 saal ke data par Sharpe 0.5 ek respectable number
hai — aur woh ek **200-day moving average** se aa raha hai, kisi cleverness se nahi.

---

## 3. Do baatein jo yahan se seekhi gayin

### (a) Financing return ka 60%+ kha jaati hai

Buy-and-hold gold: **+8.77%/saal** agar aap gold rakhein, **+2.79%/saal** is CFD
account par. Sharpe 0.643 se girkar 0.260.

Gold is arse mein +249% chala (\$1,243 → \$4,342) aur phir bhi CFD par sirf
2.79%/saal mila. **−5.66%/saal ka carry, 12.6 saal par, taqreeban aadha safar kha
gaya.**

Yeh strategy ka masla nahi. Yeh **venue** ka masla hai, aur `COSTS.md` §6 ka switch
trigger isi ke liye likha gaya tha.

### (b) Is broker par *bahar rehna* apne aap mein qeemti hai — aur yeh naya hai

Trend overlay ka faida carry ke saath **do guna** ho jata hai:

| | Bina carry | Carry ke saath | Farq |
|---|---|---|---|
| Buy and hold (vol-targeted) | 0.701 | 0.277 | −0.424 |
| 200d trend overlay | 0.814 | 0.502 | **−0.312** |

Trend overlay ~30–40% waqt flat rehta hai, aur us dauran carry nahi bharta. Yaani
overlay ka aadha faida **signal se nahi, financing bachane se** aa raha hai.

**Iska seedha asar A1 (daily trend) ke design par:** is account par ek trend filter
ki qeemat sirf yeh nahi ke woh bure trades rokta hai — woh un dinon ka **kiraya bhi
bachata hai** jab hum market mein hote hi nahi. Yeh CFD-specific hai; futures par
yeh faida nahi hoga, kyunke wahan short leg carry kamati hai.

Yeh baat P3 mein A1 ko score karte waqt alag se report hogi, warna woh signal ki
kaamyabi lagegi jabke woh broker ke rate card ka natija hai.

---

## 4. Cost model jo istemal hua

| Component | Value | Status |
|---|---|---|
| Spread | 0.12 bp round trip | **PROVISIONAL** — market band tha, `COSTS.md` §4 |
| Commission | 0.25 bp ($11/lot round turn) | **UNVERIFIED** — owner-supplied, API expose nahi karti |
| Slippage | 0.10 bp | **ASSUMPTION** — tick data abhi nahi |
| Carry long | −5.66%/yr | **MEASURED** 2026-08-08 |
| Carry short | 0.00%/yr | **MEASURED** 2026-08-08 |

**Spread per-bar archive se nahi liya gaya, aur yeh jaan-boojh kar hai.** Quality
gate ne D1 ke **32.17% bars par spread = ZERO** paya. Ek zero spread trade ko *muft*
bana deta hai. Ek imandar flat assumption ek be-imaan measurement se behtar hai.

---

## 5. Data jo mila (quality gate ke baad)

| Series | Bars | Archive claims | **Usable window** | Zero-spread bars |
|---|---|---|---|---|
| XAUUSD D1 | 3,867 | 2014→ | **2014–2026 (12.6 saal)** | 32.17% |
| XAUUSD H4 | 16,019 | 2014→ | **2017–2026** | 14.44% |
| XAUUSD H1 | 56,608 | 2014→ | **2017–2026** | 10.38% |
| XAUUSD M15 | 100,000 | 2022→ | 2022–2026 (4.2 saal) | 15.10% |
| XAGUSD D1 | 3,867 | 2014→ | **2014–2026 (12.6 saal)** | 33.33% |

**H1 aur H4 ka archive 2014 se hone ka dawa karta hai magar 2014–16 mein sirf
~5% (H1) aur ~19% (H4) bars hain** — yeh daily series hai H1/H4 ka label pehne
hue. Quality gate ne yeh khud pakra aur usable window alag report kiya.

**D1 par 12.6 saal ka poora, 100%-coverage data hai** — M15 ke 4.2 saal se teen guna.
Yeh A1 (daily trend) ko is project ka sab se achha-supported candidate banata hai,
aur woh plan ki ranking se independently mila.
