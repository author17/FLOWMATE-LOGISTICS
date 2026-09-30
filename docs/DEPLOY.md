# Publishing FLOWMATE

Two separate copies — never mix them:
1. **Practice version** (DEMO_MODE=1): fake data, orange "practice" banner, demo logins. Give this to your friend to learn.
2. **Real version** (ENV=production): empty, one real owner account, real data only.

## Easiest: Render.com (about 20-30 min, roughly €25-50/month for both copies)
1. Push this repo to GitHub (already done). Create a Render account -> New -> Blueprint -> pick the repo. `render.yaml` creates both services + databases.
2. Practice copy: open the `flowmate-practice` service -> Shell:  `python seed.py`   (creates demo users, password demo12345, banner shown)
   Reset anytime:  `python reset_demo.py`
3. Real copy: open the `flowmate` service -> Shell:
   `python create_owner.py "Her Name" her@email.com "TempPassword-123" "Gym A:gym,Gym A Cafe:cafe,Gym B:gym,Gym B Cafe:cafe"`
   She logs in and is forced to choose her own password. Then she adds staff under Users (API) / you add roles.
4. Each service gets an https:// address. Send her the practice link first.

## Own server / PC instead
`DB_PASSWORD=... SECRET_KEY=$(openssl rand -hex 32) docker compose up --build -d`, put a reverse proxy with HTTPS in front (Caddy is simplest).

## Backups (real copy)
Render paid databases include daily backups - switch them on. Also run `backend/backup.sh` daily and keep copies outside the server.
Uploaded receipts live on the persistent disk (/data); download/copy it regularly or move to S3-compatible storage later.

## Before real money/data goes in - checklist
- [ ] Practice and real copies are different web addresses and different databases
- [ ] SECRET_KEY generated (Render does it), HTTPS on
- [ ] Owner changed the temporary password; staff accounts use unique emails
- [ ] Backups switched on and one restore tested
- [ ] Accountant confirmed VAT / Cyprus cash-register handling
- [ ] Paper records kept in parallel during the pilot
## Known limits (honest list)
No two-factor login yet, no password-reset email, login lockout is per server process, bank link is CSV import only, uploaded files on a single disk.
