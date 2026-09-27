import asyncio
from dataclasses import replace
from datetime import date
import json
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from app import safe_fetch
from app.housing_models import HousingProfile, RentAssessment, PaymentQuote, PaymentRecord, QuoteRequest, Tenancy
from app.integrations import housing
from app.auth import resolve_principal
from tests.test_rent_payments import profile, tenancy, quote


def test_sources_timeout_and_property_scope(client, monkeypatch):
    p=HousingProfile(**profile('x',bbl='1000010001',bin='1000001',apartment='2A'))
    p.dataMode='real'
    calls=[]
    async def fetch(url,params=None,headers=None):
        calls.append(params)
        if 'wvxf' in url:
            return [{'violationid':'v1','apartment':'3B','bbl':p.bbl,'bin':p.bin,'novdescription':'leak','inspectiondate':'2026-09-01'}, {'violationid':'v2','apartment':'2A','bbl':p.bbl,'bin':p.bin}]
        return [{'job_id':'r1','bbl':p.bbl,'result':'Rat activity'}]
    monkeypatch.setattr(housing,'get_json',fetch)
    records,sources=asyncio.run(housing.building_records(p))
    assert [r.scope for r in records] == ['building','unit','building']
    assert all('bbl=' in c['$where'] and 'zip' not in c['$where'] for c in calls)
    assert all(s.status == 'available' for s in sources)
    async def fail(*a,**k): raise httpx.ReadTimeout('offline')
    monkeypatch.setattr(housing,'get_json',fail)
    records,sources=asyncio.run(housing.building_records(p))
    assert not records and all(s.status == 'unavailable' for s in sources)
    assert asyncio.run(housing.addresses('123 Broadway',False))['source']['status'] == 'unavailable'


def test_rentcast_does_not_invent_missing_terms(client,monkeypatch):
    async def fetch(*a,**k):
        return [{'id':'unit1','formattedAddress':'123 Broadway #1','price':2400,'squareFootage':600,'latitude':40.811,'longitude':-73.954,'lastSeenDate':date.today().isoformat(),'bedrooms':1,'bathrooms':1}]
    monkeypatch.setattr(housing,'get_json',fetch)
    p=HousingProfile(**profile('x',latitude=40.811,longitude=-73.954));p.dataMode='real';p.occupancyType='whole_apartment'
    settings=replace(client.app.state.ctx.settings,rentcast_api_key='test-provider-key')
    rows,s=asyncio.run(housing.rental_candidates(settings,p))
    assert s.status == 'available' and len(rows)==1
    assert rows[0].areaConfirmed is False and rows[0].leaseMonths is None and not rows[0].conditionsDocumented


@pytest.mark.parametrize('url',['http://127.0.0.1/private','http://169.254.169.254/latest','http://[::1]/','http://10.0.0.1/','http://localhost/','https://facebook.com/marketplace/item/1','file:///etc/passwd','http://user:pass@example.com/'])
def test_listing_private_network_block(url):
    with pytest.raises((ValueError, OSError)):
        asyncio.run(safe_fetch.public_target(url))


def test_dns_rebinding_and_redirect_revalidation(monkeypatch):
    calls=[]
    async def resolve(url):
        calls.append(url)
        if len(calls)>1: raise ValueError('private redirect')
        return httpx.URL('https://93.184.216.34/'), 'example.com'
    monkeypatch.setattr(safe_fetch,'public_target',resolve)
    original=httpx.AsyncClient
    def respond(request):
        assert request.url.host == '93.184.216.34' and request.headers['host']=='example.com'
        assert request.extensions['sni_hostname']=='example.com'
        return httpx.Response(302,headers={'location':'http://127.0.0.1/secret'})
    monkeypatch.setattr(safe_fetch.httpx,'AsyncClient',lambda **kw: original(transport=httpx.MockTransport(respond),**kw))
    with pytest.raises(ValueError,match='private redirect'):
        asyncio.run(safe_fetch.fetch_public('https://example.com/'))
    assert calls[-1]=='http://127.0.0.1/secret'


def test_supabase_auth_rejects_forgery(client,monkeypatch):
    assert client.get('/rooms',headers={'Authorization':'Bearer forged'}).status_code==401
    client.app.state.ctx.settings=replace(client.app.state.ctx.settings,supabase_url='https://test.supabase.co',supabase_publishable_key='public-test')
    original=httpx.AsyncClient
    def respond(request):
        assert request.url.path=='/auth/v1/user'
        return httpx.Response(200,json={'id':'verified-user','email_confirmed_at':'2026-01-01'}) if request.headers['authorization']=='Bearer valid' else httpx.Response(401)
    monkeypatch.setattr('app.auth.httpx.AsyncClient',lambda **kw: original(transport=httpx.MockTransport(respond),**kw))
    assert client.get('/session',headers={'Authorization':'Bearer valid'}).json()['userId']=='verified-user'
    assert client.get('/session',headers={'Authorization':'Bearer forged'}).status_code==401


def test_schema_exports_and_wire_results(client,bedroom):
    root=Path(__file__).resolve().parents[3]
    for name,model in [('housing-profile',HousingProfile),('rent-assessment',RentAssessment),('payment-quote',PaymentQuote),('payment-record',PaymentRecord),('tenancy',Tenancy),('quote-request',QuoteRequest)]:
        stored=json.loads((root/f'packages/contracts/schemas/{name}.schema.json').read_text())
        generated=model.model_json_schema();stored.pop('$id');stored.pop('$schema')
        assert stored==generated
    assessment=client.post('/rent/assess',json=profile(bedroom['roomId'])).json()['assessment']
    Draft202012Validator(RentAssessment.model_json_schema()).validate(assessment)
    t=tenancy(client,bedroom['roomId']);q=quote(client,t)
    Draft202012Validator(PaymentQuote.model_json_schema()).validate(q)
    p=client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':True}).json()['payment']
    Draft202012Validator(PaymentRecord.model_json_schema()).validate(p)
