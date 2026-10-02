# Card payments with Stripe

What it does: staff click **Card link** on an order (or **Pay link** on a member's unpaid balance). FLOWMATE creates a Stripe Checkout page;
you send the link to the customer (WhatsApp / SMS / email). When they pay, Stripe calls FLOWMATE's webhook and the order / membership is marked paid
automatically, with an audit entry. Card numbers never touch FLOWMATE - Stripe hosts the payment page.

## Set up (test mode first, about 15 minutes)
1. Create a Stripe account (stripe.com). Stay in **Test mode** until everything works. Live payments need Stripe's business verification (company details, IBAN for payouts).
2. Developers -> API keys: copy the **Secret key** (`sk_test_...`).
3. Developers -> Webhooks -> Add endpoint:
   - URL: `https://YOUR-APP-ADDRESS/api/stripe/webhook`  (Settings page in FLOWMATE shows the exact address)
   - Events: `checkout.session.completed`, `checkout.session.expired`, `checkout.session.async_payment_succeeded`
   - Copy the **Signing secret** (`whsec_...`).
4. In Railway/Render Variables add:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   APP_BASE_URL=https://YOUR-APP-ADDRESS
   ```
5. Test with Stripe test card `4242 4242 4242 4242`, any future date, any CVC. The order should flip to PAID within seconds.
6. When happy: switch Stripe to Live, replace both keys with the live ones (`sk_live_...`, new `whsec_...`).

## Safety built in
- Webhooks are accepted only with a valid Stripe signature (forged or replayed events are rejected).
- A payment is marked paid only if the amount and currency match what FLOWMATE requested; otherwise it is flagged AMOUNT_MISMATCH and a notification is created.
- Duplicate webhook deliveries are harmless.

## Good to know
- Stripe charges fees per card payment (check Stripe's current Cyprus pricing) and pays out to the bank in batches - a payout is one bank line for many orders. FLOWMATE records each order from Stripe directly, so do not match the payout line to orders.
- Refunds are done in the Stripe dashboard (not yet in FLOWMATE).
- Minimum payment about EUR 0.50.
