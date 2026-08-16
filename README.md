# gold-lab

Ek research lab aur trading system, jo pehle **"NAHI" kehna** seekhta hai — phir hi kuch banata hai.

> **NOT VALIDATED.** Yahan ki behtareen strategy ka control z-score **+0.78** hai, jabke bar
> **+2.00** hai. Uska measured Sharpe (0.499) sabit karne ke liye ~16 saal ka data chahiye;
> test window mein 6.5 thay. **Yahan ka har number ek chalta hua tajurba hai, peshangoi nahi.**
> Yeh line kabhi hatai nahi jayegi jab tak koi cheez apna control paar na kar le.

---

## Yeh kya hai

Ek XAUUSD bot ki farmaish se shuru hua. Jo bana woh us se zyada aur us se kam dono hai:
**ek falsification harness** jiska maqsad strategies ko **rad** karna hai, aur uske peeche
banaya gaya ek production system.

Ab tak **~80 pre-registered parameter combinations, 20 hypotheses, 4 timeframes, 25 markets**
test ho chuke. **Ek bhi apna random-entry control paar nahi kar saka.** Woh nakami nahi — woh
project ka sab se qeemti output hai, aur usne yeh sab **$0 mein** maloom kiya, live account
par $1,000+ mein nahi.

## Buniyadi asool

| Asool | Kahan lagu hota hai |
|---|---|
| **Look-ahead structurally na-mumkin ho** | `research/returns.py` — `shift(1)` framework lagata hai, strategy nahi |
| **Har strategy ka muqabla apne aap se** | `research/control.py` — positions rotate hoti hain: wahi turnover, wahi persistence, sirf alignment tooti hai |
| **Kitni baar dekha, uska hisab** | `research/metrics.py` — Deflated Sharpe, aur trial count P2 ki exploratory cells se shuru hota hai |
| **Pehle likho, phir test karo** | `research/prereg.py` — hash-chained log; entry badalna chain tor deta hai |
| **Costs naapo, maano mat** | `COSTS.md` — commission 598 real fills se, spread 6,503 live samples se |
| **Jo naapa nahi, usay label karo** | Har number ke saath MEASURED / ASSUMED likha hai |

## Sab se ahem test

Lab ka apna imtihaan — ek hi pipeline, do farzi duniyaon par:

| | Planted edge | Pure random walk |
|---|---|---|
| Control z | **+14.28** | +0.95 |
| Deflated Sharpe | **1.0000** | 0.0006 |
| Verdict | **PASS** | **FAIL** |

`scripts/p1_prove_the_harness.py` · Yeh permanent test suite mein hai. Agar kabhi fail ho,
kisi natije par bharosa nahi kiya ja sakta.

## Dastavezaat

| File | Kya hai |
|---|---|
| `STATUS.md` | Project abhi kahan khara hai |
| `FINDINGS.md` | **F1–F18** — har woh cheez jo naapne se mili, jismein meri apni chhe ghalat predictions aur pakde gaye bugs shamil hain |
| `COSTS.md` | Trade ka asal kharcha, measured |
| `BASELINE.md` | Woh number jise beat karna hai, kisi candidate ke banne se pehle likha gaya |
| `reports/prereg.jsonl` | Hash-chained audit trail — har hypothesis test se **pehle** darj |

## Chalane ka tareeqa

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest tests -q          # 52 tests

.venv/Scripts/python.exe scripts/p1_prove_the_harness.py   # lab khud sabit kare
.venv/Scripts/python.exe scripts/p11_fetch_universe.py     # data (MT5 chahiye)
.venv/Scripts/python.exe scripts/run_paper.py 100000       # rozana paper run
```

MetaTrader 5 terminal khula aur logged-in hona chahiye. **Broker adapter kabhi credentials
pass nahi karta** — woh sirf us account se attach hota hai jo pehle se logged in ho, aur us
module mein koi order function hai hi nahi.

## Ab tak ke chand ahem natije

- **Macro drivers explainers hain, predictors nahi** — real yields/dollar ka gold se same-date
  correlation −0.33, magar sirf published data se **−0.03** (F5)
- **Broker ka kiraya har instrument par, dono taraf** — 2% se 31%/saal. Isne multi-market book
  ko mara, signal ne nahi (F16)
- **Ek backtest path drawdown ko 1.58× kam dikhata hai** — isliye backtest gate = live limit / 1.58 (F13)
- **Jin markets mein signal hai, unhein chhote account par size nahi kiya ja sakta** — $10,000
  par gold ka minimum uske poore risk budget se bara hai (F18)
- **Gold ka nazar aane wala edge selection tha** — wahi rule 19 markets par chalao to mean
  Sharpe zero hai (F16)

## License

Private research. Koi financial advice nahi.
