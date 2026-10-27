# The `career-gps.me` domain

How CareerGPS's domain is set up, what each setting does, and how it will be used to host the app.
Update this file whenever a DNS record, sender, or hosting setting changes.

| | |
|---|---|
| Domain | `career-gps.me` |
| Registrar | Namecheap (free first year from the GitHub Student Developer Pack) |
| Registered | 2026-10-25, expires around 2027-10 (renewal about $20/year) |
| DNS | Namecheap BasicDNS (Domain List → Manage → Advanced DNS) |
| In use for | Sign-up emails (Supabase Auth through Resend) |
| Planned for | Hosting the app |

> No secrets belong in this file. API keys, passwords, and account logins stay in the services
> themselves and in private team notes.

---

## 1. Key ideas

| Term | Meaning |
|---|---|
| **Registrar** | The company you rent the name from. For us that's Namecheap. Owning the name means you control its DNS. |
| **DNS** | The internet's phone book. It answers questions like "what server is `career-gps.me`?" and "who may send email for it?" |
| **Nameservers** | The servers holding the domain's DNS records. Ours are Namecheap's (BasicDNS), so records are edited in Namecheap. |
| **DNS record** | One entry in that phone book, with a *type*, a *host* (which name it's for) and a *value*. |
| **Host `@`** | The domain itself (`career-gps.me`). Any other host is a subdomain, so `send` means `send.career-gps.me`. |
| **TTL** | How long other computers may cache a record. A change can take that long to be seen everywhere. |

| Record type | What it does | Example |
|---|---|---|
| **A** | Name → IP address | `career-gps.me` → `185.199.108.153` |
| **CNAME** | Name → another name ("look over there instead") | `www` → `career-gps.me` |
| **TXT** | Free text, used to prove ownership or publish email rules | SPF, DKIM, DMARC |
| **MX** | Where email *to* the domain is delivered | We have none; nobody receives mail at `career-gps.me` |

A **CNAME can't share its host with any other record.** Never add another record on `send` or
`rsend`, since that would break email sending.

---

## 2. Why CareerGPS needed a domain

Supabase Auth emails every new student a confirmation link. We had three problems:

1. **Supabase's built-in mailer** only delivers to members of our Supabase organization, at 2 emails per hour.
   External students couldn't sign up.
2. **Email templates were locked.** Since 3 June 2026, new free-tier Supabase projects can't edit
   auth email templates until a custom SMTP provider is connected. We needed our own template
   (`docs/supabase/confirm-signup.html`) so UW's mail scanner can't use up the single-use confirmation link.
3. **A custom SMTP provider needs a domain you own.** You can't send as `@wisc.edu` or `@gmail.com`,
   because only the owner of a domain can publish the DNS records that authorize senders. Resend's test
   sender (`onboarding@resend.dev`) only delivers to the Resend account owner.

Owning `career-gps.me` solves all three.

---

## 3. What we set up, step by step

### Step 1: Claimed the domain (Namecheap, GitHub Student Pack)
- Activated GitHub Education, then opened the Namecheap offer from education.github.com/pack.
  It goes through NC.me, Namecheap's student site, which asks to authorize your GitHub account.
- **Organization access:** didn't grant or request access to any organization.
  NC.me asks for broad repository access, so revoke it afterwards under GitHub → Settings → Applications →
  Authorized OAuth Apps → NC.me.
- Registered `career-gps.me` for $0, with WHOIS privacy on.
- The GitHub Pages **A records** and the **`www` CNAME** were already in Namecheap from the start (see the DNS map in section 4).

### Step 2: Created a Resend account and API key
- **Resend** sends the actual emails (free plan: 100/day, 3,000/month).
- Created an API key with **Sending access**. It's used as the SMTP password in Supabase and is never committed.

### Step 3: Connected Resend to Supabase (custom SMTP)
Supabase → Authentication → Emails → SMTP Settings:

| Field | Value |
|---|---|
| Host | `smtp.resend.com` |
| Port | `465` |
| Username | `resend` |
| Password | Resend API key |
| Sender name | `CareerGPS` |
| Sender email | `onboarding@resend.dev` at first, `noreply@career-gps.me` after Step 5 |

Saving this unlocked the template editor and the email rate limit.

- **Template:** Authentication → Emails → Templates → *Confirm signup* = `docs/supabase/confirm-signup.html`.
- **Rate limit:** Authentication → Rate Limits → emails = **100 / hour**.

### Step 4: Added the domain in Resend and published its DNS records
Resend → Domains → Add `career-gps.me` (region `us-east-1`). Resend generated these records, added in
Namecheap → Advanced DNS → Host Records:

| Type | Host | Value | Purpose |
|---|---|---|---|
| TXT | `resend._domainkey` | Public key from Resend (`p=MIGf…`) | **DKIM**: proves emails were really signed by us and weren't altered |
| CNAME | `send` | Value from Resend (`send.…mta.net`) | **SPF / return path**: authorizes Resend's servers to send for us, and handles bounces |
| CNAME | `rsend` | Value from Resend (`rsend.…mta.net`) | Second SPF / sending record from Resend |
| TXT | `_dmarc` | `v=DMARC1; p=none;` | **DMARC**: tells inboxes how to treat mail that fails SPF/DKIM. `p=none` = monitor only |

All records showed **Verified** in Resend on 2026-10-25.

### Step 5: Switched the sender and tested
- Changed the Supabase sender email to `noreply@career-gps.me`.
- Signed up with a Gmail address outside the team. The email arrived from `CareerGPS <noreply@career-gps.me>`,
  the confirm button worked, and onboarding completed.

---

## 4. Current DNS map

| Type | Host | Value | Used by |
|---|---|---|---|
| A | `@` | `185.199.108.153` | GitHub Pages (website, not live yet) |
| A | `@` | `185.199.109.153` | GitHub Pages |
| A | `@` | `185.199.110.153` | GitHub Pages |
| A | `@` | `185.199.111.153` | GitHub Pages |
| CNAME | `www` | `career-gps.me.` | Website (`www` → main domain) |
| TXT | `resend._domainkey` | DKIM key (from Resend) | Email |
| CNAME | `send` | Resend value | Email |
| CNAME | `rsend` | Resend value | Email |
| TXT | `_dmarc` | `v=DMARC1; p=none;` | Email |

The website records (`@`, `www`) and the email records (`send`, `rsend`, `resend._domainkey`, `_dmarc`)
use different hosts, so they never conflict. Hosting the app later doesn't touch email.

---

## 5. How a confirmation email travels

```text
Student signs up on CareerGPS
        │
        ▼
Supabase Auth ── builds the email from our "Confirm signup" template
        │        (link → {Site URL}/auth/confirm?token_hash=…)
        ▼  SMTP (smtp.resend.com:465, API key)
Resend ── signs it with DKIM, sends as noreply@career-gps.me
        │
        ▼
Student's inbox (Gmail, UW Outlook…)
   checks DNS: SPF ok? DKIM signature matches resend._domainkey? DMARC policy?
        │  all pass → inbox, not spam
        ▼
Student opens link → /auth/confirm page → presses "Confirm my email"
   (UW's scanner opens the page but never presses the button, so the link survives)
```

---

## 6. Limits

| Limit | Value |
|---|---|
| Supabase email rate limit | 100 / hour |
| Resend free plan | **100 / day**, 3,000 / month: the real ceiling |
| Supabase sign-ups and sign-ins | 30 requests / 5 min per IP |

All auth emails (confirmations, resends, future password resets) share the daily 100.

---

## 7. Planned: hosting the app on `career-gps.me`

### Target layout

| Address | Serves |
|---|---|
| `https://career-gps.me` | Frontend (Next.js) |
| `https://www.career-gps.me` | Redirects to `career-gps.me` |
| `https://api.career-gps.me` | Backend (FastAPI) |
| `noreply@career-gps.me` | Sign-up emails (already working) |

### Decide the hosts first

- **Backend:** GitHub Pages only serves static files, so FastAPI needs a server host.
  Azure App Service is a good fit for the Microsoft project; Render and Fly.io are alternatives.
- **Frontend on GitHub Pages:** needs a static export (`output: "export"`). Today's app uses server features that don't work there:
  - `frontend/proxy.ts`, the login route guard
  - `cacheComponents`

  Those would have to move to the browser or be removed.
- **Frontend on a Next.js host** (Vercel, Netlify, Azure Static Web Apps): runs the app as it is.
  The A records for `@` and the `www` CNAME would change to whatever that host gives.

### DNS to add or change when hosting

| Type | Host | Value | When |
|---|---|---|---|
| A ×4 | `@` | GitHub Pages IPs (already there) | Frontend on GitHub Pages |
| CNAME | `www` | `<account-or-org>.github.io` (GitHub's recommendation) | Frontend on GitHub Pages |
| CNAME (or A) | `api` | Backend host's address | When the backend is deployed |
| TXT | given by host | Ownership check | If the host asks to verify the domain |

### Checklist for go-live
1. Deploy the backend, add `api.career-gps.me`, and turn on HTTPS at the host.
2. Deploy the frontend, then set the custom domain to `career-gps.me` and turn on **Enforce HTTPS**.
   - On GitHub Pages: repo → Settings → Pages.
   - Also **verify the domain** (org or account settings → Pages → verified domains) so nobody else can claim it.
3. Production configuration:
   - Frontend: `NEXT_PUBLIC_API_URL=https://api.career-gps.me`
   - Backend: add `https://career-gps.me` to `CORS_ORIGINS`
4. Supabase → Authentication → URL Configuration:
   - **Site URL** = `https://career-gps.me` (confirmation emails link here)
   - **Redirect URLs** include `https://career-gps.me/**` and `http://localhost:3000/**`
5. Test sign-up end to end on the live site, including with a wisc.edu address.

Only change the Site URL after the site is live. Otherwise every confirmation email points to a page that doesn't exist.

---

## 8. Maintenance and security

- **Renewal:** about October 2027. Set a reminder a month ahead. If the domain lapses, emails and the site stop working,
  and someone else could register the name.
- **Namecheap account:** two-factor authentication on. Whoever controls it controls the domain.
- **Resend API key:** sending access only, used solely as the Supabase SMTP password. If it leaks:
  1. Revoke it in Resend.
  2. Create a new one.
  3. Update Supabase.
- **DMARC:** once sending is stable, consider moving from `p=none` to `p=quarantine` so forged mail from our domain is rejected.
- **Record changes:** don't add MX records or anything else on `send` or `rsend`.

## 9. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Email comes from `noreply@mail.app.supabase.io` | Custom SMTP is off or unsaved in Supabase |
| Sign-up says it can't send the email | Resend rejected it. Check the Resend → Emails log; the daily cap may be reached |
| Email lands in spam | New domain reputation; check DKIM/SPF are still **Verified** in Resend |
| Resend shows a record as **Failed** | Host field has `.career-gps.me` appended, the value is truncated, or another record uses the same host |
| Link says "expired or already used" | Template reverted to Supabase's default, or the Site URL is wrong |
| Template editor locked | Custom SMTP isn't configured |
