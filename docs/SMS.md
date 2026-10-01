# Text-message (SMS) login codes - optional

Two-step login works without SMS (authenticator app). SMS is an extra choice that costs a few cents per message.

1. Create a Twilio account (twilio.com), buy or register a sender (a number, or an alphanumeric sender ID where Cyprus allows it - check Twilio's Cyprus guidelines).
2. In Railway (service FLOWMATE-LOGISTICS -> Variables) add:
   - `SMS_PROVIDER` = `twilio`
   - `TWILIO_ACCOUNT_SID` = your Account SID
   - `TWILIO_AUTH_TOKEN` = your Auth Token
   - `TWILIO_FROM` = the sender number or ID
3. Redeploy. In the app, Settings -> My security -> Turn on now offers "Text message (SMS)".

Safety limits built in: one text per 30 seconds and 5 per hour per user, codes valid 5 minutes, 5 tries per code, codes work once. SMS is easier but weaker than an authenticator app (SIM-swap risk); owners who approve payments should prefer the app.
