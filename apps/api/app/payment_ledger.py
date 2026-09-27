"""Transactional payment ledger: SQLite for isolated offline demos, Postgres for Stripe test.

All checkout reservations lock the tenancy, then recheck cumulative caps. Quotes are
immutable. Remote timeouts retain the reservation for retry with the same Stripe key.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from app.config import Settings
from app.housing_models import PaymentQuote, PaymentRecord, QuoteRequest, Tenancy
from app.payments import check_payment, make_quote
from app.services import new_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS arp_fin_tenancies (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, room_id TEXT NOT NULL, doc TEXT NOT NULL, UNIQUE(user_id, room_id));
CREATE TABLE IF NOT EXISTS arp_fin_quotes (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, tenancy_id TEXT NOT NULL REFERENCES arp_fin_tenancies(id), doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS arp_fin_payments (id TEXT PRIMARY KEY, quote_id TEXT NOT NULL UNIQUE REFERENCES arp_fin_quotes(id), user_id TEXT NOT NULL, tenancy_id TEXT NOT NULL REFERENCES arp_fin_tenancies(id), session_id TEXT UNIQUE, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS arp_fin_events (id TEXT PRIMARY KEY, payment_id TEXT NOT NULL REFERENCES arp_fin_payments(id), created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS arp_fin_payments_tenancy ON arp_fin_payments(tenancy_id);
"""


class DB:
    def __init__(self, conn, postgres: bool):
        self.conn, self.postgres = conn, postgres

    def execute(self, sql: str, params: tuple = ()):
        return self.conn.execute(sql.replace("?", "%s") if self.postgres else sql, params)


class PaymentLedger:
    def __init__(self, settings: Settings, mode: str):
        self.settings, self.mode = settings, mode
        self.postgres = mode == "test"
        if self.postgres and not settings.payments_database_url:
            raise HTTPException(503, "Stripe test checkout requires PAYMENTS_DATABASE_URL and the payment migration")
        self.path = settings.data_dir / "payments-demo.sqlite3"
        if not self.postgres:
            with sqlite3.connect(self.path) as conn:
                conn.executescript(SCHEMA)

    @contextmanager
    def transaction(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(self.settings.payments_database_url, row_factory=dict_row, connect_timeout=8)
        else:
            conn = sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield DB(conn, self.postgres)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tenancy(self, db: DB, tenancy_id: str, user_id: str, lock: bool = False) -> Tenancy:
        row = db.execute("SELECT doc FROM arp_fin_tenancies WHERE id=? AND user_id=?" + (" FOR UPDATE" if lock and self.postgres else ""), (tenancy_id, user_id)).fetchone()
        if not row:
            raise HTTPException(404, "Tenancy not found")
        return Tenancy.model_validate_json(row["doc"])

    def seed(self, user_id: str, room_id: str) -> Tenancy:
        with self.transaction() as db:
            row = db.execute("SELECT doc FROM arp_fin_tenancies WHERE user_id=? AND room_id=?", (user_id, room_id)).fetchone()
            if row:
                return Tenancy.model_validate_json(row["doc"])
            t = Tenancy(id=new_id(), userId=user_id, roomId=room_id, mode=self.mode,
                        recipientId=self.settings.stripe_connected_account if self.postgres else "demo-landlord",
                        recipientName="Fictional test landlord", recipientVerified=True, leaseDocumented=True,
                        monthlyRentCents=160000, screeningActualCostCents=1800, screeningDocumentsProvided=True,
                        contact="Test fixture only — no real landlord", refundPolicy="Test payments only. No real money or deposit custody.", createdAt=datetime.now(UTC))
            db.execute("INSERT INTO arp_fin_tenancies(id,user_id,room_id,doc) VALUES(?,?,?,?) ON CONFLICT(user_id,room_id) DO NOTHING", (t.id, user_id, room_id, t.model_dump_json()))
            row = db.execute("SELECT doc FROM arp_fin_tenancies WHERE user_id=? AND room_id=?", (user_id, room_id)).fetchone()
            return Tenancy.model_validate_json(row["doc"])

    def _totals(self, db: DB, tenancy_id: str, period: str) -> dict[str, int]:
        totals: dict[str, int] = {}
        for row in db.execute("SELECT doc FROM arp_fin_payments WHERE tenancy_id=?", (tenancy_id,)).fetchall():
            p = json.loads(row["doc"])
            # Refunded/disputed amounts remain reserved pending review: no automatic cap bypass.
            if p["status"] in ("failed", "expired", "canceled"):
                continue
            if p["purpose"] == "rent_payment" and p["rentalPeriod"] != period:
                continue
            totals[p["purpose"]] = totals.get(p["purpose"], 0) + p["amountCents"]
        return totals

    def quote(self, user_id: str, request: QuoteRequest) -> PaymentQuote:
        with self.transaction() as db:
            t = self._tenancy(db, request.tenancyId, user_id, True)
            q = make_quote(t, request, self._totals(db, t.id, request.rentalPeriod))
            db.execute("INSERT INTO arp_fin_quotes(id,user_id,tenancy_id,doc) VALUES(?,?,?,?)", (q.id, user_id, t.id, q.model_dump_json()))
            return q

    def get_quote(self, user_id: str, quote_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT doc FROM arp_fin_quotes WHERE id=? AND user_id=?", (quote_id, user_id)).fetchone()
            if not row:
                raise HTTPException(404, "Quote not found")
            return json.loads(row["doc"])

    def reserve(self, user_id: str, quote_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT doc FROM arp_fin_quotes WHERE id=? AND user_id=?", (quote_id, user_id)).fetchone()
            if not row:
                raise HTTPException(404, "Quote not found")
            q = PaymentQuote.model_validate_json(row["doc"])
            t = self._tenancy(db, q.tenancyId, user_id, True)
            existing = db.execute("SELECT doc FROM arp_fin_payments WHERE quote_id=?", (q.id,)).fetchone()
            if existing:
                return json.loads(existing["doc"])
            if q.expiresAt <= datetime.now(UTC):
                raise HTTPException(409, "Quote expired; review a new quote")
            if q.mode != self.mode or q.recipientId != t.recipientId or q.currency != "usd":
                raise HTTPException(409, "Quote no longer matches the tenancy")
            decision, reasons = check_payment(t, QuoteRequest(tenancyId=t.id, purpose=q.purpose, amountCents=q.amountCents, rentalPeriod=q.rentalPeriod), self._totals(db, t.id, q.rentalPeriod))
            if decision != "ready" or q.decision != "ready":
                raise HTTPException(409, {"decision": decision, "reasons": reasons})
            now = datetime.now(UTC)
            p = PaymentRecord(id=new_id(), quoteId=q.id, userId=user_id, roomId=t.roomId, tenancyId=t.id, recipientId=t.recipientId, purpose=q.purpose, rentalPeriod=q.rentalPeriod, amountCents=q.amountCents, mode=self.mode, status="created", createdAt=now, updatedAt=now)
            db.execute("INSERT INTO arp_fin_payments(id,quote_id,user_id,tenancy_id,doc) VALUES(?,?,?,?,?)", (p.id, q.id, user_id, t.id, p.model_dump_json()))
            return p.model_dump(mode="json")

    def _payment(self, db: DB, payment_id: str, user_id: str | None = None, lock: bool = False) -> dict:
        params = (payment_id, user_id) if user_id else (payment_id,)
        sql = "SELECT doc FROM arp_fin_payments WHERE id=?" + (" AND user_id=?" if user_id else "") + (" FOR UPDATE" if lock and self.postgres else "")
        row = db.execute(sql, params).fetchone()
        if not row:
            raise HTTPException(404, "Payment not found")
        return json.loads(row["doc"])

    def get(self, payment_id: str, user_id: str | None = None) -> dict:
        with self.transaction() as db:
            return self._payment(db, payment_id, user_id)

    def list(self, user_id: str, room_id: str | None = None) -> list[dict]:
        with self.transaction() as db:
            rows = [json.loads(r["doc"]) for r in db.execute("SELECT doc FROM arp_fin_payments WHERE user_id=?", (user_id,)).fetchall()]
            return sorted([p for p in rows if room_id is None or p["roomId"] == room_id], key=lambda p: p["createdAt"], reverse=True)

    def _save(self, db: DB, p: dict) -> dict:
        p["updatedAt"] = datetime.now(UTC).isoformat()
        # Validate every persisted transition against the shared contract.
        doc = PaymentRecord.model_validate(p).model_dump_json()
        db.execute("UPDATE arp_fin_payments SET doc=?,session_id=? WHERE id=?", (doc, p.get("sessionId"), p["id"]))
        return json.loads(doc)

    def attach_session(self, payment_id: str, session: dict) -> dict:
        with self.transaction() as db:
            p = self._payment(db, payment_id, lock=True)
            if p["status"] == "created":
                p["status"] = "pending"
            p.update(sessionId=session["id"], checkoutUrl=session.get("url"), paymentIntentId=session.get("payment_intent") or p.get("paymentIntentId"))
            return self._save(db, p)

    def apply_event(self, event_id: str, payment_id: str, status: str, *, intent_id: str | None = None, refunded: int = 0) -> dict:
        with self.transaction() as db:
            p = self._payment(db, payment_id, lock=True)
            inserted = db.execute("INSERT INTO arp_fin_events(id,payment_id,created_at) VALUES(?,?,?) ON CONFLICT(id) DO NOTHING", (event_id, payment_id, datetime.now(UTC).isoformat()))
            if inserted.rowcount == 0:
                return p
            # Replayed older events cannot undo settlement, refunds, or an open dispute.
            ranks = {"created": 0, "pending": 1, "failed": 2, "canceled": 2, "expired": 2, "succeeded": 3, "refunded": 4, "disputed": 5}
            if ranks[status] >= ranks[p["status"]]:
                p["status"] = status
            p["refundedCents"] = max(p.get("refundedCents", 0), refunded)
            p["paymentIntentId"] = intent_id or p.get("paymentIntentId")
            return self._save(db, p)
