# SmartSafe V27 QR Fix & Perf Optimization TODO

## Current Task: Fix QR Login Tab (Real QR) + Ensure Superfast

### Steps

- [ ] **1. Create TODO.md** ✅ *Done*
- [ ] **2. Edit ui/tabs/qr_login_tab.py**
  - Add "New Session" account option (fresh Baileys session)
  - Custom session name input
  - On select: api.connect_account(session_name) → real QR
  - Hide/remove demo "default" QR
  - Mimic MultiAccount real QR flow
- [ ] **3. Test QR Tab**: New Session → Real QR appears → Scan works
- [ ] **4. Verify Perf**: No added lag (threading unchanged)
- [ ] **5. attempt_completion**

**Perf Status**: Already optimized (daemons/async/UI batches).

Proceeding to edit...
