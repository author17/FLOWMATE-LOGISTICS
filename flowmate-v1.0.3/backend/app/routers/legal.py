"""Privacy policy and terms pages (the app stores require a public privacy-policy URL). TEMPLATE TEXT: have a lawyer review it before launch."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from .. import config

router = APIRouter()
CSS = "<meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{font-family:system-ui;max-width:760px;margin:auto;padding:20px;line-height:1.55;color:#1d2733}h1{color:#0f3d5e}h2{margin-top:1.6em}</style>"

def _privacy():
    c, e = config.LEGAL_COMPANY, config.LEGAL_EMAIL
    return f"""{CSS}<title>Privacy Policy - FLOWMATE</title><h1>Privacy Policy</h1><p>Last updated: 2026. Operator: <b>{c}</b>. Contact: <a href="mailto:{e}">{e}</a>.</p>
<h2>What FLOWMATE is</h2><p>FLOWMATE is a business-management app (orders, stock, invoices, documents, staff). Each business that signs up has its own private workspace; other businesses cannot see its data.</p>
<h2>What we store</h2><p>Account data (name, e-mail, hashed password, optional phone number for text-message login codes); the business data you enter or upload (customers, products, orders, invoices, scanned documents and photos, bank transactions you connect or import); and security logs (login time, browser/device type, IP address).</p>
<h2>Camera and photos</h2><p>The camera is used only when you choose to photograph a document. Text recognition runs on your device; the file is then saved in your business workspace.</p>
<h2>How we use it</h2><p>Only to run the service for your business, keep it secure, and provide support. We do not sell data and do not show advertising.</p>
<h2>Service providers</h2><p>Hosting and database (cloud provider), optional text-message delivery, optional payment processing (Stripe) and optional bank connection (an Open Banking provider) - only if you or your business turn these on.</p>
<h2>Security</h2><p>Data is encrypted in transit; sensitive keys are encrypted at rest; passwords are hashed; optional two-step login is available.</p>
<h2>Retention and deletion</h2><p>Your data is kept while your account is open. The owner can delete the whole business, and any user can delete their own login, inside the app (Settings &rarr; Delete account). Deletion removes the data from the live system; encrypted backups are overwritten within 30 days.</p>
<h2>Your rights</h2><p>You can access, export (Settings &rarr; Data &amp; backups), correct or delete your data, and complain to your data-protection authority (in Cyprus: the Commissioner for Personal Data Protection). Write to <a href="mailto:{e}">{e}</a>.</p>
<h2>Children</h2><p>FLOWMATE is for businesses and is not directed at children.</p>"""

def _terms():
    c, e = config.LEGAL_COMPANY, config.LEGAL_EMAIL
    return f"""{CSS}<title>Terms - FLOWMATE</title><h1>Terms of Use</h1><p>Operator: <b>{c}</b>. Contact: <a href="mailto:{e}">{e}</a>.</p>
<p>By creating an account you agree to these terms and to the <a href="/privacy">Privacy Policy</a>.</p>
<h2>Your account</h2><p>You are responsible for your login, for the people you add as users, and for the accuracy of what you enter. Keep your password private.</p>
<h2>Your data</h2><p>Your business data belongs to you. You give us permission to store and process it only to provide the service. You can export or delete it at any time.</p>
<h2>Not professional advice</h2><p>FLOWMATE helps organise accounting and tax information (for example VAT figures and automatic document reading) but does not replace an accountant. Check important figures before relying on them.</p>
<h2>Acceptable use</h2><p>Do not misuse the service, try to access other businesses' data, or upload unlawful content.</p>
<h2>Availability</h2><p>We work to keep the service running and back it up, but we do not guarantee it will always be available or error-free, and we are not liable for indirect losses to the extent the law allows.</p>
<h2>Changes and ending</h2><p>We may update these terms and will tell you about important changes. You can close your account at any time; we may suspend accounts that break these terms.</p>"""

@router.get("/privacy", include_in_schema=False)
def privacy(): return HTMLResponse(_privacy())

@router.get("/terms", include_in_schema=False)
def terms(): return HTMLResponse(_terms())
