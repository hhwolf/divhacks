# Housing comparisons and guarded test payments

The Rent panel extends the existing designer. Physical measurements are confirmed separately from furniture placement. It supports manual housing-condition reports, private photos, comparable asking rents, property records, furnishing budgets and explicit payment review. Materials scoring and new computer vision are excluded.

## Run the offline demonstration

Use the normal `make api` and `make web` setup with `MOCK_MODE=true`, `PAYMENTS_MODE=demo` and no service credentials. If your `.env` has storage/provider credentials, clear those when running an isolated offline demo. Set `PUBLIC_WEB_URL` to the same web origin you are using; otherwise checkout returns to the wrong port.

1. Load the NYC bedroom sample. The rental onboarding panel opens. Confirm its 109.8 sq ft physical area, private-room occupancy, room-only coverage, 12-month lease, unfurnished status and excluded utilities. Select **Demo data**.
2. Add **Rats / rodents** or **Leaks / water damage**, ongoing, moderate, inside the unit. Optionally attach a JPEG/PNG/WebP up to 5 MB. Save the details and compare asking rents.
3. The 24 synthetic comparable units produce a baseline median of $1,330 and middle-half range $1,265–$1,395. Six comparable rooms reporting moderate rodents produce a median of $1,225; the observed median difference is −$105, **not** a causal discount. Leaks and combined problems have their own synthetic examples. Public records shown in this mode are also synthetic.
4. Close Rent and choose **Import furniture**. Enter a room divider’s dimensions, price and delivery, confirm dimensions, then preview it. Try putting it across the doorway: the existing validator flags door clearance. Existing bounds/overlap checks block saving; doorway/path findings remain visible in Fit. Purchasing uses **Open original listing**. The app neither processes nor protects that external sale; a divider does not create a lawful bedroom.
5. Return to Rent → Budget & payments → **Load test tenancy**. This immutable fictional tenancy documents $1,600 rent and an $18 screening cost; it is unrelated to your market comparison.
6. Review a $75 application processing fee: blocked. A $1,601 security deposit is also blocked. A documented screening reimbursement above $18 is blocked even though it is below $20.
7. Review a $1,600 rent payment, read the recipient/purpose/period/amount/contact/refund information, explicitly confirm, and continue. Without Stripe configuration this opens an **offline simulation**. Click **Simulate successful payment**. It is never described as a Stripe charge.

Automated browser runs, using isolated opaque demo sessions:

```sh
.venv/bin/python scripts/e2e_housing.py --web http://localhost:5173
.venv/bin/python scripts/e2e_editor.py --web http://localhost:5173 --api http://localhost:8000
.venv/bin/python scripts/demo.py --web http://localhost:5173 --api http://localhost:8000
```

Screenshots/results are written under `.context/housing-demo/` and `.context/designer-demo/`. The designer test covers real pointer dragging, rotating, locking, undo, validation, persistence and variants. Photon imports pause for dimension confirmation before a fit recommendation; its updated demo confirms the imported dimensions and then requests a variant. No real message is sent in mock mode.

## Enable private workspaces

Apply `migrations/001_payment_ledger.sql` to Postgres. For Supabase, also apply `migrations/002_supabase_access.sql` in the SQL editor. Migration 002 creates the document table if necessary, enables RLS, limits authenticated document reads to their owner, revokes client writes, denies all direct client access to financial tables, and creates a **private** `housing-evidence` storage bucket. Existing permissive policies must be reviewed before deployment; the migration does not authorize public storage policies.

Set server-only `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (or legacy service-role key) and `SUPABASE_PUBLISHABLE_KEY`. Set `VITE_SUPABASE_URL` / `VITE_SUPABASE_PUBLISHABLE_KEY` and the corresponding `EXPO_PUBLIC_*` values to the **same project and public key**. Configure Supabase email OTP; the email template must include `{{ .Token }}`. Email delivery and sign-in need a configured Supabase project.

The web home page and mobile Settings have email/code sign-in. Bearer tokens are verified against Supabase Auth on every protected API request, not decoded without verification. Authenticated mobile scans and the trusted editor WebView share the session; demo scans share a per-device random secret. The native auth client refreshes tokens while active. Sign-out/account changes reload the trusted WebView; tokens are never injected into seller pages or Stripe pages. Changing the native server URLs is a trusted developer setting. Rebuild the native app after installing its new Expo Crypto dependency.

Every API repository access checks ownership even when its server key bypasses RLS. Tenancies, immutable quotes and payments have owner checks inside their SQL transactions. Condition photos have authenticated API reads, `private, no-store` responses, private storage, image decoding/re-encoding that strips metadata, a 5 MB/20-megapixel limit and deletion controls. They are never passed to Gemini. Furniture screenshots remain part of the existing, separate AI import feature.

Sign-in opens a separate private workspace; anonymous demo data is not automatically reassigned to an account. Legacy no-header CLI calls share only a synthetic namespace and cannot upload condition photos. Use a random `X-Demo-Session` for browser/CLI interoperability. Keep local JSON/SQLite demo storage on a trusted development machine; serverless temporary demo files are ephemeral.

Room preferences and the Backboard assistant identifier are saved with the workspace user and reused across later requests. Creating another room does not reset them.

For live Photon, configure the signed webhook, verify a phone number on the **same Supabase user** (Supabase phone update + OTP verification), then call authenticated `POST /session/link-phone`. The API derives the verified phone from Auth and never trusts a submitted phone/owner. Unknown senders receive no private-room information. The first MVP supports the most recent room for that linked account, with dimension confirmation in the editor.

## Stripe test checkout

The implementation is test-only. It accepts `PAYMENTS_MODE=demo|stripe_test`, rejects live secret keys at startup, rejects live Stripe objects/events, and uses no platform commission. Never place secret keys or the database DSN in Vite/Expo variables.

1. Apply migration 001 to a persistent Postgres database. Use a server-only connection role authorized for the four `arp_fin_*` tables, with SSL for hosted databases. The JSON document store and Photon outbox are never the financial ledger.
2. Configure a Stripe Connect platform in **test mode**. Set `STRIPE_SECRET_KEY=sk_test_…`. Run `.venv/bin/python scripts/seed_stripe_test.py` to create/reuse a fictional Express test landlord; it prints an `acct_…` identifier, not secrets. Complete its test onboarding and enable card payments. Set `STRIPE_CONNECTED_ACCOUNT` to that account.
3. Set `PAYMENTS_MODE=stripe_test`, `PAYMENTS_DATABASE_URL`, `STRIPE_WEBHOOK_SECRET` and the correct `PUBLIC_WEB_URL`. Authentication is required to enter Stripe test mode; anonymous sessions still use the separate demo ledger.
4. Configure a **Connect account events** webhook at `/webhooks/stripe`, including `checkout.session.completed`, `checkout.session.expired`, `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`, `charge.refunded`, `charge.dispute.created`, `charge.dispute.updated` and `charge.dispute.closed`. With Stripe CLI, forward connected events using `stripe listen --forward-connect-to localhost:8000/webhooks/stripe` and use its printed signing secret. Provider dashboard/CLI setup can change; use [Stripe's Connect webhook guide](https://docs.stripe.com/connect/webhooks).
5. Sign in, create/load a private sample room, then perform steps 5–7 of the walkthrough. The button now reads **Continue to Stripe test checkout**. Use Stripe’s documented test card `4242 4242 4242 4242`, any future expiry and any CVC. An actual connected-account test charge should appear in Stripe, with no platform application fee. The return page remains pending until a verified webhook confirms settlement.
6. Exercise a decline, expiration, refund and dispute in the Stripe test dashboard. A declined card remains retryable within Checkout and retains its reservation until expiration/cancellation; an expired session with a confirmed decline is recorded as failed. Full refunds and disputes are represented in history; partial refund cents are recorded. Disputes remain conservatively flagged for operations review even after provider closure. There is no refund/custody operations UI in this MVP.

Checkout accepts only `{ "quoteId": "…", "confirmed": true }`. Quotes bind payer, recipient, tenancy, purpose, amount in integer cents, currency and a 30-minute expiry. The server rechecks caps while locking the tenancy. A unique quote-to-payment constraint and a persistent Stripe idempotency key prevent duplicate sessions for retries. Timeouts retain reservations; after 20 hours an unresolved attempt requires reconciliation instead of a new Stripe request that could outlive Stripe’s idempotency retention. Distinct quotes permit intentional partial payments up to cumulative caps. Refunds/disputes do not automatically release caps.

Signed webhooks validate the connected account, test mode and amount/currency. The handler retrieves current provider state, writes payment state and event deduplication transactionally, and prevents older success/failure events from undoing refunds/disputes. Redirect query parameters never establish payment success. Unrelated Connect events are ignored. Legacy mock payment documents remain legacy demo records outside this ledger; `/payments/supabase-sync` is retired with HTTP 410.

## Comparison method and data provenance

| Source | Adapter and limitations | Verification in this implementation |
|---|---|---|
| Physical area | Shoelace area of existing immutable floor polygon; user confirms coverage and may correct reported area without changing geometry | Fixtures, manual rooms, partial-apartment rejection, furniture invariance tested |
| [RentCast rental listings](https://developers.rentcast.io/reference/rental-listings-long-term) | Server-side key, radius/property/bedroom query, 8-second timeout, 1-hour cache; listing area and missing lease/utilities/furnished terms require explicit review. Provider IDs/observation dates retained. Provider documentation URL is shown when no original listing URL is supplied; add the original URL during review | HTTP adapter tested with representative responses; actual paid-provider query requires `RENTCAST_API_KEY` |
| Private rooms | User-entered source URL, distinct room identifier, observed date, confirmed area/coordinates, lease/utilities/furnishing, shared amenities and explicitly documented matching problems | Synthetic fixtures and manual-entry path tested; no apartment-rent-per-bedroom allocation |
| [NYC GeoSearch](https://geosearch.planninglabs.nyc/docs/) | Multiple address candidates displayed for user choice; PAD BBL/BIN retained; never uses ZIP to imply a property match | Live request returned candidates for a public sample address |
| [HPD violations](https://data.cityofnewyork.us/Housing-Development/Housing-Maintenance-Code-Violations/wvxf-dwi5) | Latest 200 records queried by BBL, narrowed by BIN when present; unit scope only for exact apartment match. Violations/inspection dates and current statuses retained | Live request succeeded; timeout/scope tests pass. This is not a complete complaints or repair-history feed |
| [Rodent inspections](https://data.cityofnewyork.us/Health/Rodent-Inspection/p937-wjvj) | BBL/BIN matching, latest 200 inspections, results/date/source retained; building scope, never automatic evidence of rats in a room | Live request succeeded; no-records/unavailable remain explicit |
| [StreetEasy](https://streeteasy.com/blog/data-dashboard/) and [HUD SAFMR](https://www.huduser.gov/portal/datasets/fmr/smallarea/index.html) | Curated, authorized snapshots only; separate neighborhood/program context; no scraping or private-room valuation | No snapshots shipped; explicitly unavailable. `scripts/import_housing_benchmarks.py` validates authorized JSON with source/ZIP/mode/label/value/observedAt/retrievedAt/sourceUrl/permittedUse |
| Synthetic fixtures | `fixtures/housing/comparables.json`, relative observation dates; synthetic building records | Explicit Demo data labels. Unavailable real sources never substitute these |

Source metadata includes retrieval/observation dates, URLs, statuses and reuse notes. Provider data is cached only in-process (maximum 256 queries); missing configuration/timeouts yield unavailable. Benchmark snapshots are cached by the filesystem and retain their original observation/retrieval dates. StreetEasy reuse needs permission/terms review; no redistribution license is assumed. Review NYC/HUD/RentCast terms before production redistribution.

Qualifying listings match occupancy type, lease duration, included utilities, furnishing and location; whole apartments/studios also match bedroom/bathroom counts and require whole-apartment coverage. Defaults: observed in the past 90 days, within one mile, within ±25% confirmed physical area; newest unique units first, up to 25. Unit identifiers normalize case/spacing and duplicate URLs are removed. User-entered location/details remain user assertions. With at least five records, linear-interpolated 25th, 50th and 75th percentiles are rounded to dollars; otherwise show examples and **Insufficient comparable data**. These are product defaults, not validated valuation standards. NYC calendar dates are used consistently.

The second calculation uses only comparable units with explicit condition documentation and the same set of current, ongoing unit-level issue categories/severities. Unknown severity/status, old evidence, building-only observations, resolved conditions and missing evidence do not establish a condition match. At least five matches are required. No regression/causal interpretation, universal deduction, material rating, furniture-layout penalty or lawful-rent calculation exists. HCR rent history guidance is linked separately. Serious-condition reporting notices remain visible independently of price; the app does not recommend withholding contractual rent.

## Payment checks and production gates

Rules `nyc-residential-2026-09-26-v1` were reviewed September 26, 2026 against [NY Attorney General guidance](https://ag.ny.gov/publications/residential-tenants-rights-guide), [RPL §238-a](https://www.nysenate.gov/legislation/laws/RPP/238-A) and [NYC FARE Act guidance](https://www.nyc.gov/site/dca/about/FAQ-Broker-Fees.page). They cover the supported ordinary residential test tenancy only. They are not comprehensive legal eligibility determinations.

- Deposits use documented contractual rent, plus recorded and reserved deposits, against the applicable one-month cap. Missing lease/recipient evidence requires review.
- Covered screening fees require documentation, are cumulatively capped at the lesser of actual cost and $20, and are waived for a qualifying recent report. Generic processing fees do not pass merely because they are small.
- Landlord-hired broker fees are blocked. Tenant-hired/unknown broker arrangements require review. Other unknown charges and unverified recipients require review.
- Condition and market findings are advisory and never automatically block contractual rent. No assistant endpoint creates or authorizes payment.

Live mode has no enable switch. Before adding one, complete recipient authority and property/tenancy verification (Stripe identity alone is insufficient), processor approval for the rental use case, legal scope review and update ownership, deposit trust/custody requirements, reconciliation/timeout recovery, refund/dispute operations, audit retention, rate limiting/abuse controls, monitoring, backup/restore and privacy/account deletion policies. Seeded recipient verification is explicitly fictional test data; the MVP does not accept arbitrary client-authored lease or recipient facts.

## Tests

Verified in this workspace: 108 API tests (103 credential-free cases plus five optional Postgres cases), 29 JavaScript tests, 14/14 designer pointer checks, the Photon import/variant demo, the housing browser flow and mobile-width panel check. Web/mobile type checks, lint and the production web build pass. No actual Stripe charge, Supabase email login or device LiDAR capture was executed without their credentials/hardware.

```sh
pnpm typecheck
pnpm lint
pnpm test
pnpm --filter @arp/web build
npm --prefix apps/mobile run typecheck
.venv/bin/python -m pytest -q apps/api/tests
# Optional but recommended: a DISPOSABLE local PostgreSQL database, never production
ARP_TEST_DATABASE_URL=postgresql://localhost/arp_test .venv/bin/python -m pytest -q apps/api/tests/test_stripe_postgres.py
.venv/bin/python scripts/export_housing_schemas.py
```

The Postgres suite creates a unique schema, applies migration 001, tests actual SQL locking/uniqueness and removes only that schema. Stripe HTTP responses are simulated; the actual Stripe SDK verifies HMAC signatures. Tests cover retries, replay, out-of-order events, refunds/disputes, amount tampering, cross-user denial and redirect-without-payment. Supabase JWT verification is tested against mocked Auth responses; a real project is needed to verify deployed email delivery, RLS/storage and device sign-in end to end. LiDAR hardware capture was preserved but not exercised on an iPhone in this implementation run.

Pydantic is the source for six housing/financial JSON Schemas; schema drift and serialized API responses are tested. Keep `packages/contracts/src/index.ts` aligned when changing wire fields. Existing fixture assessments without a calculation version return `legacy_demo` and no market range until reassessed.
