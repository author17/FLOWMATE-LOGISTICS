# Publishing FLOWMATE on Google Play and the App Store

## What is built (v1.0)
* Many separate businesses on one server. Every business sees ONLY its own data (enforced in the database layer, 16 leak tests).
* Public sign-up (business name, type, owner, e-mail, password, accept Terms) - no gym/café wording, types: Café/restaurant, Gym, Retail shop, Other/mixed.
* Account deletion inside the app (My account) - owner deletes the whole business, staff delete their own login. Required by both stores.
* Privacy Policy `/privacy` and Terms `/terms` pages (TEMPLATE text - have a lawyer read it; set LEGAL_COMPANY and LEGAL_EMAIL on Railway).
* Capacitor wrapper in `mobile/` (Android + iOS), native camera for document photos.

## Railway variables to add before launch
* `PLATFORM_ADMIN_EMAILS` = your e-mail (only you may download the all-business nightly backups)
* `LEGAL_COMPANY` = your company/trading name, `LEGAL_EMAIL` = support address shown in the policy
* `SIGNUP_ENABLED` = 1 (set 0 to close sign-up), `SIGNUPS_PER_IP_HOUR` = 5
* Keep SECRET_KEY unchanged forever.

## Android (Google Play)
1. Install Android Studio. In PowerShell: `cd C:\Projects\flowmate\frontend; $env:VITE_API_BASE="https://flowmate-logistics-production.up.railway.app"; npm install; npm run build:mobile`
2. `cd ..\mobile; npm install; npx cap sync android; npx cap open android`
3. Android Studio: Build > Generate Signed App Bundle (AAB). CREATE A KEYSTORE AND BACK IT UP IN 2 PLACES - lose it and you can never update the app. Use Play App Signing.
4. Play Console: create app, upload the AAB to Internal testing first. Fill: Data safety (collects: name, e-mail, phone (optional), photos/documents, financial info the user enters; encrypted in transit; deletion possible in app + web URL), Content rating, Target audience 18+, Privacy policy URL `https://<your-domain>/privacy`, account-deletion URL (same site: log in > My account).
5. NEW PERSONAL developer accounts must run a closed test with testers for a minimum period before production access (rule changed over time - check the current requirement in Play Console). An organisation account avoids it.
6. App access: reviewers can create their own account (sign-up is open) - say so in "App access" notes.

## iPhone (App Store) - no Mac needed
1. Push the repo (including `mobile/`) to GitHub. Create the app in App Store Connect (bundle id `com.flowmate.logistics` - permanent once created; change appId in `mobile/capacitor.config.json` first if you want another).
2. Codemagic.io: add the repo, create an App Store Connect API key integration named FLOWMATE_ASC, use `mobile/codemagic.yaml`. It builds, signs and uploads to TestFlight.
3. App Store Connect: privacy nutrition labels (same answers as Data safety), screenshots 6.7" and 6.5" iPhone, support URL, privacy URL, age rating, and in App Review notes explain: "Create a business account on the first screen with any e-mail".
4. Apple guideline 4.2 (minimum functionality) is the main rejection risk for web-wrapped apps. FLOWMATE uses the native camera and is a genuine business tool with login, which helps; if rejected, the next step is adding push notifications and biometric unlock (not built yet).

## Things that must be true before charging money or promising anything
* Stripe / Enable Banking / SMS / Claude receipt reading: never tested with real accounts.
* Payment *initiation* from a bank needs a regulated licence; FLOWMATE only reads statements and prepares payments.
* E-mail verification at sign-up and subscription billing are NOT built yet (in-app purchase rules: Apple takes 15-30% if you sell the subscription inside the iPhone app; selling to businesses outside the app has its own rules - decide before pricing).
* Have an accountant check VAT rules; have a lawyer read Privacy/Terms.
