"""Run with ARP_TEST_DATABASE_URL pointing at a disposable Postgres database.
Stripe HTTP is simulated; signature verification and database transactions are real.
"""
import hashlib
import hmac
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from app.auth import Principal
from app.main import create_app
from app.payment_ledger import PaymentLedger
from app.payments import StripeTest
from tests.test_rent_payments import tenancy, quote


@pytest.fixture
def pg(client, monkeypatch):
    url=os.environ.get('ARP_TEST_DATABASE_URL')
    if not url: pytest.skip('Set ARP_TEST_DATABASE_URL to run Postgres/Stripe contract tests')
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    schema='arp_test_'+uuid.uuid4().hex
    with psycopg.connect(url,autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    test_url=make_conninfo(url, options=f'-c search_path={schema}')
    with psycopg.connect(test_url) as conn:
        conn.execute((Path(__file__).resolve().parents[3]/'migrations/001_payment_ledger.sql').read_text())
    settings=replace(client.app.state.ctx.settings,payments_mode='stripe_test',payments_database_url=test_url,stripe_secret_key='sk_test_fixture',stripe_webhook_secret='whsec_fixture',stripe_connected_account='acct_fixture')
    client.app.state.ctx.settings=settings
    async def identity(request): return Principal(request.headers.get('x-test-user','user-a'),True)
    monkeypatch.setattr('app.deps.resolve_principal',identity)
    yield settings
    with psycopg.connect(url,autocommit=True) as conn:
        conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def seed(client):
    r=client.post('/rooms',json={'sample':'nyc-bedroom'}).json()['room']['id']
    return tenancy(client,r)


def event(client, kind, obj, *, event_id=None, account='acct_fixture', live=False, timestamp=None):
    payload={'id':event_id or 'evt_'+uuid.uuid4().hex,'object':'event','type':kind,'livemode':live,'account':account,'data':{'object':obj}}
    raw=json.dumps(payload).encode();ts=timestamp or int(time.time())
    sig=hmac.new(b'whsec_fixture',str(ts).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    return client.post('/webhooks/stripe',content=raw,headers={'stripe-signature':f't={ts},v1={sig}'})


def test_stripe_checkout_webhooks_and_reconciliation(client,pg,monkeypatch):
    t=seed(client);q=quote(client,t);requests=[];current={'status':'succeeded','amount':50000,'currency':'usd','latest_charge':None}
    original=httpx.AsyncClient
    def provider(req):
        requests.append(req)
        assert req.headers['Stripe-Account']=='acct_fixture'
        if req.method=='POST':
            from urllib.parse import parse_qs
            data=parse_qs(req.content.decode())
            assert data['line_items[0][price_data][unit_amount]']==['50000']
            assert 'application_fee_amount' not in req.content.decode()
            current['metadata']={'payment_id':data['client_reference_id'][0]}
            assert req.headers['Idempotency-Key']=='arp-test-'+current['metadata']['payment_id']
            return httpx.Response(200,json={'id':'cs_test_fixture','url':'https://checkout.stripe.com/c/pay/cs_test_fixture','payment_intent':'pi_fixture','livemode':False})
        return httpx.Response(200,json={'id':'pi_fixture','livemode':False,**current})
    monkeypatch.setattr('app.payments.httpx.AsyncClient',lambda **kw:original(transport=httpx.MockTransport(provider),**kw))
    response=client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':True});assert response.status_code==200,response.text
    p=response.json()['payment'];assert p['mode']=='test' and p['status']=='pending'
    assert client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':True}).json()['payment']['id']==p['id']
    assert len(requests)==1
    assert client.get(f"/payments/{p['id']}?success=true").json()['payment']['status']=='pending'
    assert client.get(f"/payments/{p['id']}",headers={'x-test-user':'user-b'}).status_code==404
    assert client.post(f"/payments/{p['id']}/simulate",json={'outcome':'succeeded'}).status_code==403
    assert client.post('/webhooks/stripe',content=b'{}',headers={'stripe-signature':'bad'}).status_code==400
    obj={'id':'pi_fixture'}
    assert event(client,'payment_intent.succeeded',obj,timestamp=int(time.time())-600).status_code==400
    assert event(client,'payment_intent.succeeded',obj,account='acct_wrong').status_code==400
    assert event(client,'payment_intent.succeeded',obj,live=True).status_code==400
    current['amount']=1
    assert event(client,'payment_intent.succeeded',obj).status_code==400
    current['amount']=50000
    assert event(client,'payment_intent.succeeded',obj,event_id='evt_success').json()['status']=='succeeded'
    assert event(client,'payment_intent.succeeded',obj,event_id='evt_success').json()['status']=='succeeded'
    current['latest_charge']={'amount_refunded':10000}
    event(client,'charge.refunded',{'payment_intent':'pi_fixture'})
    assert client.get(f"/payments/{p['id']}").json()['payment']['refundedCents']==10000
    current['latest_charge']={'amount_refunded':50000}
    assert event(client,'charge.refunded',{'payment_intent':'pi_fixture'}).json()['status']=='refunded'
    current['latest_charge']=None
    assert event(client,'payment_intent.succeeded',obj).json()['status']=='refunded'
    current['latest_charge']={'disputed':True,'amount_refunded':50000}
    assert event(client,'charge.dispute.created',{'payment_intent':'pi_fixture'}).json()['status']=='disputed'
    assert event(client,'payment_intent.payment_failed',obj).json()['status']=='disputed'


def test_uncertain_checkout_retries_same_idempotency_key(client,pg,monkeypatch):
    t=seed(client);q=quote(client,t);keys=[]
    async def provider(self,method,path,data=None,idempotency=None):
        keys.append(idempotency)
        if len(keys)==1: raise HTTPException(503,'provider timeout')
        return {'id':'cs_test_retry','url':'https://checkout.stripe.com/test'}
    monkeypatch.setattr(StripeTest,'request',provider)
    assert client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':True}).status_code==503
    assert client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':True}).status_code==200
    assert keys[0]==keys[1]
    assert len(PaymentLedger(pg,'test').list(t['userId']))==1


def test_postgres_race_caps_and_unique_quotes(client,pg):
    t=seed(client);q1=quote(client,t,100000);q2=quote(client,t,100000);db=PaymentLedger(pg,'test')
    def reserve(q):
        try:return db.reserve(t['userId'],q['id'])['id']
        except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,[q1,q2]))
    assert results.count(409)==1
    winner=q1 if results[0]!=409 else q2
    with ThreadPoolExecutor(max_workers=5) as pool:assert len(set(pool.map(reserve,[winner]*5)))==1


def test_expired_sessions_release_reservations(client,pg,monkeypatch):
    t=seed(client);q=quote(client,t,160000);db=PaymentLedger(pg,'test');p=db.reserve(t['userId'],q['id']);db.attach_session(p['id'],{'id':'cs_test_expired'})
    async def provider(self,method,path,data=None,idempotency=None):
        return {'id':'cs_test_expired','status':'expired','client_reference_id':p['id'],'amount_total':160000,'currency':'usd'}
    monkeypatch.setattr(StripeTest,'request',provider)
    result=event(client,'checkout.session.expired',{'id':'cs_test_expired','client_reference_id':p['id']})
    assert result.status_code==200,result.text
    assert result.json()['status']=='expired'
    assert quote(client,t,160000)['decision']=='ready'


def test_live_mode_rejected_at_startup(client):
    with pytest.raises(ValueError,match='live payments'):
        create_app(replace(client.app.state.ctx.settings,payments_mode='live'))
    with pytest.raises(ValueError,match='test secret'):
        create_app(replace(client.app.state.ctx.settings,stripe_secret_key='sk_live_forbidden'))


def test_decline_then_expiration_marks_failed(client,pg,monkeypatch):
    t=seed(client);q=quote(client,t);db=PaymentLedger(pg,'test');p=db.reserve(t['userId'],q['id']);db.attach_session(p['id'],{'id':'cs_test_declined','payment_intent':'pi_declined'})
    async def provider(self,method,path,data=None,idempotency=None):
        if path.startswith('payment_intents/'):
            return {'id':'pi_declined','amount':50000,'currency':'usd','status':'requires_payment_method','last_payment_error':{'code':'card_declined'},'metadata':{'payment_id':p['id']}}
        return {'id':'cs_test_declined','status':'expired','client_reference_id':p['id'],'amount_total':50000,'currency':'usd'}
    monkeypatch.setattr(StripeTest,'request',provider)
    assert event(client,'payment_intent.payment_failed',{'id':'pi_declined'}).json()['status']=='pending'
    assert event(client,'checkout.session.expired',{'id':'cs_test_declined','payment_intent':'pi_declined'}).json()['status']=='failed'
