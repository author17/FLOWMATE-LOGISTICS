# Status vs blueprint (v0.4)
Built with screens: dashboard, orders (multi-item, customer, payment method), customers, suppliers, products, stock + purchase orders, invoices, expenses, receipts/documents + OCR (needs API key),
banking (CSV import, matching, reconciliation), payments (sandbox bank), documents, reports (12, PDF/Excel/CSV), notifications, users & permissions, settings, audit, exports, delivery, gym memberships, Stripe card links, assistant, PWA.

Still open (honest list):
1. Live bank connection (Eurobank): needs an Open Banking provider account + a sample statement; importer adapts to the real CSV format first.
2. Two-factor login, password-reset email.
3. Till/POS daily sales import (need the tills' export format).
4. Stripe refunds, receipts by email, recurring membership billing (direct debit / card on file).
5. Object storage (S3) for documents; automated backups; invoice line items editing in UI; stock transfer between locations.
6. Accountant review: VAT rates per product, cash-register rules, Cyprus e-invoicing requirements.
7. Native Android/iOS apps (the installable web app works on phones now).
