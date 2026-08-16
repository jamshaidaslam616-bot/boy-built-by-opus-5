# GUIDE.md — chalane ka tareeqa

> **Yeh abhi paper mode hai. Koi order nahi jata.** `execution/paper.py` mein koi aisa raasta
> hai hi nahi jo terminal ke order functions tak jaye. Live karne ke liye alag kaam chahiye
> jo abhi hua nahi.

---

## 1. Rozana kya karna hai

Bas **ek command**, din mein **ek baar**, daily close ke baad:

```powershell
cd C:\gold-lab
.venv\Scripts\python.exe scripts\run_paper.py 100000
```

Aakhri number aap ka capital hai. Har run yeh karta hai:

1. 25 markets ke closed daily bars parhta hai (banti hui bar **nahi** — woh look-ahead hoti)
2. 120-din ke return par rank karta hai, top 7 long aur bottom 7 short chunta hai
3. Jo positions book se nikal gayin, jinka side badal gaya, ya jo **7-din window ke qareeb**
   hain — band karta hai
4. Nayi positions kholta hai, risk engine ki ijazat se
5. Sab kuch journal mein likhta hai — **refusals bhi**

### Output mein kya dekhna hai

```
carried in: 13 open legs · equity $99,988.98 · peak $100,000.00 · drawdown 0.01%
```

- **`carried in`** — agar yeh **0** hai aur pehla din nahi hai, to state file gum ho gayi. Ruk
  kar dekhein, chalate na rahein.
- **`drawdown`** — 20% par bot **khud ruk jayega** aur khud clear nahi hoga
- **`refused`** — yeh **buri khabar nahi** hai. Iska matlab risk engine ne ek aisi position
  rok di jo aap ke risk budget se bari thi. Kabhi kabhi refusal hona sehatmand hai.

### Halt ho jaye to

Bot rukta hai aur `paper_state.json` mein halt likha rehta hai. **Pehle samjhein kyun rukka**
(journal mein `action='HALTED'` dekh lein), phir hi clear karein. Jo halt khud clear ho jaye
woh halt nahi, sirf ek intezaar hai.

---

## 2. Kya dekh sakte hain

```powershell
# aakhri 20 faisle, wajah ke sath
.venv\Scripts\python.exe -c "import sqlite3,sys; [print(r) for r in sqlite3.connect(r'reports\paper.sqlite').execute('SELECT bar_utc,symbol,action,reason FROM decisions ORDER BY id DESC LIMIT 20')]"

# equity curve
.venv\Scripts\python.exe -c "import sqlite3; [print(r) for r in sqlite3.connect(r'reports\paper.sqlite').execute('SELECT bar_utc,equity,drawdown_pct,open_legs FROM equity_curve ORDER BY bar_utc')]"

# sab tests — kuch bhi shak ho to yeh chalayein
.venv\Scripts\python.exe -m pytest tests -q
```

Journal **append-only** hai. Koi row kabhi badalti ya mitti nahi. Isi liye "March mein yeh
trade kyun li thi" ka jawab mahinon baad bhi mil sakta hai.

---

## 3. Alag VPS par chalane ka tareeqa

MT5 sirf **Windows** par chalta hai, isliye Windows VPS chahiye. 2 GB RAM kaafi hai.

### Qadam 1 — VPS lein

Koi bhi Windows Server VPS (Contabo, Vultr, AWS Lightsail — ~$10–20/mahina). **Region wahan
chunein jahan aap ka broker server ho** — Exness ke liye Europe theek hai.

### Qadam 2 — MT5 install karke login karein

1. Exness se MT5 download karein, install karein
2. **Apne account se login karein aur "Remember password" tick karein** — taake VPS reboot ke
   baad woh khud login ho jaye
3. Terminal khula chhor dein. **Bot terminal ko launch nahi karta, us se attach hota hai.**

### Qadam 3 — Python aur code

```powershell
# Python 3.12 install karein (python.org se), phir:
cd C:\
git clone https://github.com/jamshaidaslam616-bot/boy-built-by-opus-5.git gold-lab
cd C:\gold-lab
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Qadam 4 — pehle sab kuch verify karein

**Yeh skip na karein.** Teen cheezein, is tarteeb mein:

```powershell
# 1. sab tests pass hone chahiyen
.venv\Scripts\python.exe -m pytest tests -q

# 2. lab khud ko sabit kare — planted edge PASS, random walk FAIL
.venv\Scripts\python.exe scripts\p1_prove_the_harness.py

# 3. broker connection aur costs
.venv\Scripts\python.exe scripts\p0_recon.py
```

Agar #2 fail ho jaye to **aage na barhein** — jo lab apne aap ko sabit na kar sake, uske kisi
natije par bharosa nahi kiya ja sakta.

### Qadam 5 — data

```powershell
.venv\Scripts\python.exe scripts\p11_fetch_universe.py
.venv\Scripts\python.exe scripts\p18_wide_universe.py
```

(Data git par nahi hai — 13MB hai aur broker se minute mein aa jata hai.)

### Qadam 6 — rozana khud chalne ka intezam

Task Scheduler mein ek task banayein:

- **Trigger:** roz, **23:30 UTC** (daily close ke baad, magar naye din ki open se pehle)
- **Action:** `C:\gold-lab\.venv\Scripts\python.exe`
- **Arguments:** `C:\gold-lab\scripts\run_paper.py 100000`
- **Start in:** `C:\gold-lab`
- ✅ *Run whether user is logged on or not*

Ya PowerShell se:

```powershell
$a = New-ScheduledTaskAction -Execute "C:\gold-lab\.venv\Scripts\python.exe" `
     -Argument "C:\gold-lab\scripts\run_paper.py 100000" -WorkingDirectory "C:\gold-lab"
$t = New-ScheduledTaskTrigger -Daily -At 11:30PM
Register-ScheduledTask -TaskName "gold-lab-paper" -Action $a -Trigger $t -RunLevel Highest
```

### Qadam 7 — backup

Do file **kabhi na khoyein**:

| File | Kyun |
|---|---|
| `reports/paper.sqlite` | Poora out-of-sample record. Yeh khoya to ghadi **zero se** shuru hogi |
| `reports/paper_state.json` | Current book. Yeh khoya to bot samjhega uske paas kuch nahi hai aur sab dobara khol dega |

Hafte mein ek baar git par push kar dein — remote pehle se set hai.

### VPS par khayal rakhne wali baatein

- **MT5 ek waqt mein ek account par logged in rehta hai.** Us VPS par koi doosra bot na
  chalayein — jo bhi aakhir mein login kare wohi jeet ta hai.
- **Windows Update reboot** kar sakta hai. MT5 ko startup par auto-run set kar dein.
- Bot kabhi credentials use nahi karta — woh jo bhi account logged in ho us se attach hota
  hai. Iska matlab: **hamesha check karein ke terminal sahi account par hai.**

---

## 4. Ab kya baqi hai

| Kaam | Halat | Kyun ahem hai |
|---|---|---|
| **Production sizing ka backtest** | **BAQI** | P19 ka +0.499 continuous sizing par tha. Jo ab chalti hai woh minimum lot par round-down karti hai, silver skip karti hai, 7-din par roll karti hai. **Woh number alag hoga**, aur jab tak woh na naapa jaye main koi expected return quote nahi karunga |
| Telegram alerts | Nahi bana | Halt aur bara drawdown phone par pata chalna chahiye |
| Demo par real orders | Nahi | Paper aur asli fills ka farq naapne ke liye |
| Live trading | **Nahi, aur main khud enable nahi karunga** | Uske liye aap ka explicit flag aur typed phrase chahiye |

### Aur sab se ahem baat, jo main dohraata rahunga

Is strategy ka **control z = +0.78** hai, jabke bar **+2.00** hai. Uska Sharpe (0.499) sabit
karne ke liye ~16 saal ka data chahiye; abhi **72 saal ka 1 din** hai.

**Yeh bot paisa banane ke liye nahi chal raha. Yeh us sawal ka jawab jama karne ke liye chal
raha hai ke isme koi edge hai bhi ya nahi.** Har din jo woh chalta hai, ek observation banta
hai. Woh ghadi ab chal rahi hai — aur uske ilawa is sawal ka koi shortcut nahi hai.
