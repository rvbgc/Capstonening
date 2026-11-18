# SMISHGUARD prototype — startup and demo guide

SMISHGUARD is a capstone prototype that checks English SMS messages for
smishing (SMS phishing). It combines a preliminary machine-learning
classifier with a separate PhishHunt URL check, and supports screenshot
input (OCR), consent-based reporting, and optional private history.

This guide covers starting the prototype, running the demo, and the
limitations to state honestly during the presentation.

---

## 1. What the prototype does

| Feature | How it works |
|---|---|
| Typed message check | User pastes an English SMS (1–5,000 characters) and taps **Analyze Message**. |
| Screenshot input | User selects a PNG/JPEG screenshot (≤ 5 MB). The backend runs Tesseract OCR and returns editable text for the user to review before analysis. |
| SMS assessment | TF-IDF + linear SVM model returns `smishing` or `non_smishing`, with general safety advice. |
| URL check | Links in the message are compared with a cached PhishHunt feed. Shown in a **separate card** from the model result. |
| Reports | User can submit a message for review after a consent dialog. Reports start as **pending** and are reviewed through protected admin API endpoints. |
| Accounts | Register, sign in, sign out. Passwords are hashed; sessions expire after 12 hours. |
| Private history | Opt-in per analysis. Latest 100 saved analyses per account. View, delete one, clear all. |
| Account deletion | Password-confirmed. Deletes the account, all its sessions, and all its saved history. |

---

## 2. Components to start

All four must be running for the full demo:

1. **PostgreSQL 18** service (database `smishguard`, role `smishguard_app`)
2. **FastAPI backend** (port 8000)
3. **PhishHunt feed updater** (keeps the URL cache fresh)
4. **Android emulator** (`emulator-5554`) or a physical phone with the app

### 2.1 PostgreSQL

PostgreSQL normally starts with Windows. To check, open **Services**
(`services.msc`) and confirm the `postgresql-x64-18` service is **Running**.

### 2.2 Backend (PowerShell window 1)

```powershell
cd "C:\Users\Ralph Vincent Gamad\Capstonening\backend"
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Leave this window open. Check it in a second window:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10 | ConvertTo-Json
```

Expected: `"status": "ok"` and `"model_ready": true`.

Interactive API documentation: <http://127.0.0.1:8000/docs>

Do not start a second backend if one is already running on port 8000.

### 2.3 Feed updater (PowerShell window 2)

```powershell
cd "C:\Users\Ralph Vincent Gamad\Capstonening\backend"
.\.venv\Scripts\python.exe auto_refresh_threat_feed.py
```

It refreshes the PhishHunt cache every hour (retries after 5 minutes on
failure). Leave this window open.

### 2.4 Emulator app (PowerShell window 3)

Start the emulator from Android Studio, then:

```powershell
cd "C:\Users\Ralph Vincent Gamad\Capstonening\mobile"
flutter build apk --debug
flutter install --debug -d emulator-5554
```

The emulator reaches the PC's backend at `http://10.0.2.2:8000` (the
app's default). In the emulator browser, `http://10.0.2.2:8000/health`
should show the same health response.

Installing a new build can clear the saved sign-in; sign in again if asked.

**Emulator time zone:** set **Settings → System → Date & time → Time zone**
to **Philippines (Manila)** so history times show in local time.

---

## 3. Running on a physical Android phone (optional)

The phone and the PC must be on the **same Wi-Fi network**.

1. **Find the PC's Wi-Fi address** (PowerShell):

   ```powershell
   ipconfig
   ```

   Use the **IPv4 Address** under the Wi-Fi adapter, e.g. `192.168.1.23`.

2. **Allow port 8000 through Windows Firewall** (PowerShell **as
   Administrator**, one time only):

   ```powershell
   New-NetFirewallRule -DisplayName "SMISHGUARD API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
   ```

   The Wi-Fi network must be set to **Private** in Windows settings.

3. **Start the backend listening on the network** instead of only on the PC:

   ```powershell
   cd "C:\Users\Ralph Vincent Gamad\Capstonening\backend"
   .\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```

   Only do this on a trusted network (home or a private hotspot), and stop
   it after the demo.

4. **Test from the phone's browser:** open `http://192.168.1.23:8000/health`
   (use your own address). It must show `"status":"ok"` before continuing.

5. **Build the app with the PC's address** and install it. Enable
   **Developer options → USB debugging** on the phone, connect it by USB,
   then:

   ```powershell
   cd "C:\Users\Ralph Vincent Gamad\Capstonening\mobile"
   flutter devices
   flutter build apk --debug --dart-define=API_BASE_URL=http://192.168.1.23:8000
   flutter install --debug -d <device-id-from-flutter-devices>
   ```

The app's **Check server connection** message shows which address it is
using if the connection fails, which helps diagnose a wrong address.

If the PC's address changes (different Wi-Fi), rebuild with the new address.

---

## 4. Demo sequence (about 10 minutes)

1. **Server status.** Open the app. It checks the server automatically:
   *"Server connected. Model is available."*
2. **Typed smishing example.** Paste a message with a link, e.g. a fake
   parcel-fee message. Tap **Analyze Message**. Point out the two separate
   cards:
   - **SMS assessment** (model result, marked preliminary)
   - **URL check (PhishHunt)** (feed result; *not listed* does not mean safe)
3. **Ordinary message.** Analyze a normal message to show the neutral
   result. Note that "not detected" does not confirm the message is safe.
4. **Screenshot input.** Tap **Select screenshot**, choose an SMS
   screenshot, and show that the extracted text appears for review and
   editing before analysis.
5. **Report.** Tap **Report Message**, read the consent dialog, submit, and
   show the *Pending review* receipt.
6. **Account and history.** Tap the account icon, sign in, return, tick
   **Save this analysis to my history**, analyze, and open the saved entry
   in history. Show that unticked analyses are not saved.
7. **Privacy controls.** Delete one history entry; mention **Clear my
   history** and **Delete my account** (password-confirmed).
8. **Admin review (optional).** Show the protected report endpoints at
   <http://127.0.0.1:8000/docs> (admin token required).

---

## 5. Checks to run before the demo

Backend checks (backend running, from the `backend` folder):

```powershell
.\.venv\Scripts\python.exe check_auth.py
.\.venv\Scripts\python.exe check_history.py
.\.venv\Scripts\python.exe check_account_deletion.py
```

Each prints `PASS` lines and creates/removes its own temporary accounts.

App checks (from the `mobile` folder):

```powershell
flutter analyze
flutter test
```

---

## 6. Screenshot evaluation (for the paper)

Keep screenshots **outside** the repository; they may contain personal
information. Example folder: `C:\dev\smishguard-screenshots`.

```powershell
cd "C:\Users\Ralph Vincent Gamad\Capstonening\backend"
.\.venv\Scripts\python.exe evaluate_screenshots.py "C:\dev\smishguard-screenshots"
```

1. The first run creates `labels.csv` in that folder. Fill in
   `expected_label` for each screenshot: `smishing` or `non_smishing`
   (`legitimate`, `spam` and `ordinary_spam` are also accepted and counted
   as `non_smishing`).
2. Run the same command again. It writes:
   - `evaluation_results.csv` — OCR text, prediction, URL status per image
   - `evaluation_summary.md` — OCR success rate, accuracy, precision,
     recall, confusion matrix, URL-check counts, failures

The evaluation uses raw OCR text without the manual review step the app
asks users to do, so it is a stricter test than real use.

---

## 7. Model evaluation (current model)

Model version: `trial_20261117_140834_470042` (TF-IDF + linear SVM).

| Item | Value |
|---|---|
| Eligible English messages | 245 |
| Training / held-out test | 196 / 49 |
| Held-out accuracy | 71.4% |
| Held-out composition | 29 smishing, 20 ordinary spam, 0 legitimate |

Confusion matrix (rows = actual, columns = predicted):

| | non_smishing | smishing |
|---|---|---|
| **non_smishing** | 10 | 10 |
| **smishing** | 4 | 25 |

- Detected 25 of 29 smishing examples (4 missed).
- Classified 10 of 20 ordinary-spam examples as smishing.
- The test set has **no legitimate SMS**, so false positives on ordinary
  personal or business messages cannot be measured from it.

---

## 8. Data storage and security

| Data | Where | Notes |
|---|---|---|
| Accounts | PostgreSQL `users` | Passwords hashed (not reversible). |
| Sessions | PostgreSQL `user_sessions` | Only a SHA-256 hash of each token is stored; 12-hour expiry. |
| Session on the phone | Android secure storage | Encrypts the token on the device only. |
| Saved history | PostgreSQL `analysis_history` | Opt-in; latest 100 per account; deleted with the account. |
| Reports | PostgreSQL `reports` | Not linked to accounts; kept when history or an account is deleted. |
| Admin access | Separate `ADMIN_API_TOKEN` in `backend/.env` | User sessions cannot access admin endpoints. |

Never commit `backend/.env` or any admin token file. The repository is
public.

---

## 9. Limitations (state these honestly)

- **Preliminary model.** Small dataset (245 messages), 71.4% held-out
  accuracy, no legitimate-SMS test data.
- **Binary output only.** No risk levels, no calibrated confidence, and no
  message-specific explanation of why a message was flagged.
- **English only.** Taglish and Filipino messages are not supported.
- **URL check is a cached feed match.** *Not listed* does not mean a link
  is safe; new phishing links may not be listed yet.
- **OCR can misread text.** Users must review extracted text; a screenshot
  does not prove a message is authentic.
- **Local prototype.** Plain HTTP on a local network, no public hosting, no
  HTTPS, no database encryption at rest.
- **No password recovery.**
- **Admin review is API-only**; there is no admin dashboard.
- **Reports are not verified** and are not automatically used as training
  data.

## 10. Future work

Larger and more balanced dataset including legitimate SMS; Taglish/Filipino
support; calibrated risk levels and explanations; HTTPS hosting with
encrypted storage; password recovery; an admin review dashboard.
