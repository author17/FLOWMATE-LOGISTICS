# Bank connection (live bank feed)

FLOWMATE reads balances and transactions through **Enable Banking** (PSD2 Open Banking, read-only). It never moves money and never sees the bank password.
Each business owner connects, syncs, renews and disconnects their own bank **inside the app**: Settings -> Bank connections.

## One-time setup (per deployment)
1. Create an account at enablebanking.com, open the Control Panel and register an application (choose the environment you need; start with *sandbox*, then request *production* access for your real accounts).
2. Set the application's **redirect URL** to `APP_BASE_URL/api/bank/callback` (shown on the Settings screen).
3. Download the application's private key (PEM). Either
   - set the variables `ENABLEBANKING_APP_ID` and `ENABLEBANKING_PRIVATE_KEY` on the server, **or**
   - paste the Application ID and key in Settings -> Bank connections (stored encrypted; the owner can change or remove them).
4. Choose country + bank (e.g. Cyprus -> Eurobank) and press **Connect**. The bank's own page asks for approval; access lasts up to 90 days and the app reminds the owner 14 days before it ends ("Renew access").

Whether the provider allows one application to serve many different customers depends on their agreement: check this with Enable Banking before selling to other businesses.

## How payments work
Bank payments are **prepare -> owner approves -> pay in the bank's own app**. The statement line then completes the payment automatically. (Initiating payments from software requires a payment-institution licence or a licensed partner.)

## Practice mode
With `DEMO_MODE=1` and no provider keys a "Demo Bank (practice)" is offered so staff can learn the whole flow.
