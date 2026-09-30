# FLOWMATE LOGISTICS
Your business's digital assistant.

Orders → Stock → Documents → Suppliers → Payments → Delivery → Banking

*From the first order to the final payment — FLOWMATE keeps everything connected.*

(v0.5 - all blueprint modules have screens; see docs/ROADMAP.md for what is still open.)

Stack: Python FastAPI + SQLAlchemy (SQLite now, PostgreSQL later) + React (Vite).

## Run it
```
cd backend
pip install -r requirements.txt
python seed.py                      # demo data: 2 gyms + 2 cafes, users, supplier, invoice
uvicorn app.main:app --reload       # API on :8000 (docs at /docs)
cd ../frontend && npm install && npm run build   # then open http://localhost:8000
# or for development: npm run dev  (http://localhost:5173)
```
Demo logins (password `demo12345`): owner@ / manager@ / cashier@ / accountant@ / payer@ / driver@demo.com

Tests: `cd backend && python -m pytest`

## What works now
Delivery: delivery jobs per order, driver assignment, status flow (Prepared > On the way > Delivered/Failed), photo proof, drivers only see their own jobs, delivered = order completed. Note: stock is deducted when an order is created (not at delivery).
Login + roles, locations, customers, suppliers, products, orders (auto stock deduction), supplier invoices (duplicate protection),
expenses, receipt/invoice upload + OCR + human review, cashier shift cash-up with difference alert, bank statement CSV import +
auto-matching + suggestions + confirm, payment workflow (sandbox bank; never COMPLETED without provider confirmation),
low-stock purchase orders, dashboard per location, audit log, notifications, CSV export of every table.

## Structure
- `backend/app/models.py`      database schema (money stored as integer cents)
- `backend/app/banking/`       BANK INTEGRATION LAYER: `base.py` interface, `csv_provider.py`, `sandbox_provider.py`. Add a bank = new class + register.
- `backend/app/ocr/`           OCR layer: `mock` (default) or `claude` (set OCR_PROVIDER=claude and ANTHROPIC_API_KEY)
- `backend/app/services/`      matching engine, payment state machine
- `backend/app/routers/`       REST API per area;  `security.py` roles;  `audit.py` audit + notifications
- `frontend/src/`              React screens;  `storage/` uploaded originals (move to S3-compatible storage in production)

## Before real use (not done yet)
Set SECRET_KEY; HTTPS; switch to PostgreSQL; MFA; real Open Banking provider class; encrypted backups; password change/reset;
mobile app (the web app already opens the camera on phones); Cyprus VAT/cash-register rules checked with an accountant; no claim of replacing accounting software.

## Publishing
See docs/DEPLOY.md (Dockerfile, docker-compose.yml, render.yaml included). Practice copy = DEMO_MODE=1 with fake data; real copy = ENV=production + create_owner.py.

## v0.4 adds
Gym memberships (plans, members, check-in, renewals, balances), 12 reports as PDF/Excel/CSV, Stripe card payment links, business assistant, user management, settings, notifications bell, customers/products/expenses/purchase-order screens, installable phone app (PWA), real-system bootstrap via BOOTSTRAP_* variables.


## Live bank feed
See docs/BANKING.md. Optional environment variables added in v0.5: SMTP_HOST/PORT/USER/PASS/FROM (e-mail alerts & purchase orders), INBOUND_EMAIL_TOKEN (forward supplier invoices by e-mail), ENABLEBANKING_APP_ID/ENABLEBANKING_PRIVATE_KEY, BANK_SYNC_HOURS, REQUIRE_MFA_ROLES.
