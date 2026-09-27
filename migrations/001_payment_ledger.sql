-- Transactional test ledger. Apply with a server-side Postgres role.

CREATE TABLE IF NOT EXISTS arp_fin_tenancies (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, room_id TEXT NOT NULL, doc TEXT NOT NULL, UNIQUE(user_id, room_id));
CREATE TABLE IF NOT EXISTS arp_fin_quotes (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, tenancy_id TEXT NOT NULL REFERENCES arp_fin_tenancies(id), doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS arp_fin_payments (id TEXT PRIMARY KEY, quote_id TEXT NOT NULL UNIQUE REFERENCES arp_fin_quotes(id), user_id TEXT NOT NULL, tenancy_id TEXT NOT NULL REFERENCES arp_fin_tenancies(id), session_id TEXT UNIQUE, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS arp_fin_events (id TEXT PRIMARY KEY, payment_id TEXT NOT NULL REFERENCES arp_fin_payments(id), created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS arp_fin_payments_tenancy ON arp_fin_payments(tenancy_id);
