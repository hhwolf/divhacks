from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
import io
import json

import pytest
from fastapi import HTTPException
from PIL import Image

from app.housing_models import HousingProfile, QuoteRequest
from app.integrations.housing import demo_comparables
from app.payment_ledger import PaymentLedger
from app.payments import check_payment
from app.rent import comparison_range, eligible_comparables, polygon_area_sqft


def profile(room_id, **patch):
    return dict(roomId=room_id, askingRent=1600, occupancyType='private_room', scanCoverage='room', measurementConfirmed=True,
                confirmedAreaSqFt=109.8, leaseMonths=12, furnished=False, utilitiesIncluded=False, dataMode='demo', **patch)


def issue(category='rodents', **patch):
    return dict(category=category, status='ongoing', severity='moderate', scope='unit', source='user', observedAt=date.today().isoformat(), **patch)


def test_condition_comparison_and_geometry_invariance(client, bedroom):
    body = profile(bedroom['roomId'], conditions=[issue()])
    a = client.post('/rent/assess', json=body).json()['assessment']
    assert a['status'] == 'demo' and len(a['comparables']) == 24
    assert a['conditionMatchedRange'] and len(a['conditionComparableIds']) == 6
    assert a['conditionDifference'] == a['conditionMatchedRange']['mid'] - a['estimatedFairRange']['mid']
    assert all(r['scope'] == 'building' for r in a['buildingRecords'])
    assert any('not a proven causal' in x for x in a['explanation'])
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={}).json()
    client.put(f"/layouts/{fork['id']}", json={'items': [], 'source': 'editor'})
    b = client.post('/rent/assess', json={**body, 'layoutId': fork['id']}).json()['assessment']
    assert a['estimatedFairRange'] == b['estimatedFairRange']
    assert a['spaceQuality']['floorAreaSqFt'] == b['spaceQuality']['floorAreaSqFt']
    assert a['spaceQuality']['usableAreaSqFt'] != b['spaceQuality']['usableAreaSqFt']
    assert polygon_area_sqft([(0,0),(2,0),(2,1),(1,1),(1,2),(0,2)]) == 32.3


@pytest.mark.parametrize('patch', [{'measurementConfirmed': False}, {'occupancyType':'whole_apartment','scanCoverage':'room'}, {'leaseMonths':6}, {'confirmedAreaSqFt':900}])
def test_insufficient_matching(client, bedroom, patch):
    response = client.post('/rent/assess', json={**profile(bedroom['roomId']), **patch})
    assert response.status_code == 201
    assert response.json()['assessment']['estimatedFairRange'] is None


def test_no_real_fallback_or_zip_claims(client, bedroom):
    r = client.post('/rent/assess', json={**profile(bedroom['roomId'], zip='10027', conditions=[issue()]), 'dataMode':'real'}).json()['assessment']
    assert r['status'] == 'insufficient_data' and not r['comparables'] and not r['buildingRecords']
    assert r['conditionMatchedRange'] is None
    assert 'These problems may affect value, but we do not have enough comparable evidence to quantify the effect.' in r['explanation']
    assert all(s['status'] != 'demo' for s in r['sources'])


@pytest.mark.parametrize('field,value', [('status','resolved'), ('status','unknown'), ('severity','unknown'), ('scope','building'), ('observedAt','2000-01-01')])
def test_condition_evidence_must_match(client, bedroom, field, value):
    c = {**issue(), field:value}
    a = client.post('/rent/assess', json=profile(bedroom['roomId'], conditions=[c])).json()['assessment']
    assert a['estimatedFairRange'] and a['conditionMatchedRange'] is None


def test_eligibility_dedup_age_missing_and_apartment_terms():
    p = HousingProfile(**profile('room', latitude=40.811, longitude=-73.954))
    comps = demo_comparables()
    assert comparison_range(comps[:4]) is None
    assert comparison_range(comps[:5]) is not None
    c = comps[0]
    mutations = [dict(observedAt=date.today()-timedelta(days=91)), dict(observedAt=date.today()+timedelta(days=1)),
                 dict(latitude=41), dict(areaConfirmed=False), dict(areaSqFt=300), dict(leaseMonths=None),
                 dict(utilitiesIncluded=True), dict(furnished=True), dict(occupancyType='whole_apartment')]
    invalid = [c.model_copy(update={**m, 'id':str(i),'unitKey':str(i),'sourceUrl':f'https://example.invalid/{i}'}) for i,m in enumerate(mutations)]
    assert eligible_comparables(p, invalid, 110) == []
    duplicates = [c, c.model_copy(update={'id':'copy','unitKey':' SYNTHETIC UNIT 0-0 '})]
    assert len(eligible_comparables(p, duplicates, 110)) == 1
    assert len(eligible_comparables(p, comps, 110)) == 24
    whole = p.model_copy(update={'occupancyType':'whole_apartment', 'scanCoverage':'whole_apartment','bedrooms':2,'bathrooms':1})
    assert eligible_comparables(whole, [c],110) == []
    apartment = c.model_copy(update={'occupancyType':'whole_apartment','bedrooms':2,'bathrooms':1})
    assert eligible_comparables(whole, [apartment],110) == [apartment]
    assert eligible_comparables(whole, [apartment.model_copy(update={'bathrooms':2})],110) == []


def tenancy(client, room_id):
    response = client.post('/payments/test-tenancy', json={'roomId':room_id})
    assert response.status_code == 201, response.text
    return response.json()['tenancy']


def quote(client, t, amount=50000, purpose='deposit'):
    response = client.post('/payments/quote', json={'tenancyId':t['id'], 'amountCents':amount, 'purpose':purpose, 'rentalPeriod':'2026-09'})
    assert response.status_code == 201, response.text
    return response.json()['quote']


def test_payment_rules_and_cumulative_caps(client, bedroom):
    t = tenancy(client, bedroom['roomId'])
    assert quote(client,t,160001)['decision'] == 'blocked'
    assert quote(client,t,100,'application_fee')['decision'] == 'blocked'
    assert quote(client,t,1801,'screening_fee')['decision'] == 'blocked'
    first = quote(client,t,100000)
    assert first['decision'] == 'ready'
    assert client.post('/payments/checkout',json={'quoteId':first['id'],'confirmed':True}).status_code == 200
    assert quote(client,t,60001)['decision'] == 'blocked'
    assert quote(client,t,100,'broker_fee')['decision'] == 'needs_review'
    assert quote(client,t,100,'other')['decision'] == 'needs_review'
    db = PaymentLedger(client.app.state.ctx.settings,'demo')
    from app.housing_models import Tenancy
    model = Tenancy(**t)
    req = QuoteRequest(tenancyId=t['id'],purpose='screening_fee',amountCents=100,rentalPeriod='2026-09')
    for patch,decision in [({'recentScreeningReport':True},'blocked'),({'screeningDocumentsProvided':False},'needs_review'),({'screeningActualCostCents':None},'needs_review'),({'screeningAlreadyPaidCents':1750},'blocked')]:
        assert check_payment(model.model_copy(update=patch),req,{})[0] == decision
    assert check_payment(model.model_copy(update={'brokerHiredBy':'landlord'}),req.model_copy(update={'purpose':'broker_fee'}),{})[0] == 'blocked'
    assert check_payment(model.model_copy(update={'recipientVerified':False}),req,{})[0] == 'needs_review'
    assert check_payment(model.model_copy(update={'leaseDocumented':False}),req.model_copy(update={'purpose':'deposit'}),{})[0] == 'needs_review'
    assert db.list(t['userId'])


def test_checkout_tampering_expiry_duplicate_and_redirect(client, bedroom):
    t = tenancy(client,bedroom['roomId']); q = quote(client,t)
    assert client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':False}).status_code == 409
    assert client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':True,'amountCents':1}).status_code == 422
    for amount in [1.1, '100', -1]:
        assert client.post('/payments/quote',json={'tenancyId':t['id'],'purpose':'deposit','amountCents':amount,'rentalPeriod':'2026-09'}).status_code == 422
    a = client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':True}).json()['payment']
    b = client.post('/payments/checkout',json={'quoteId':q['id'],'confirmed':True}).json()['payment']
    assert a['id'] == b['id'] and a['status'] == 'pending'
    assert client.get(f"/payments/{a['id']}?success=true").json()['payment']['status'] == 'pending'
    q2 = quote(client,t,100)
    db = PaymentLedger(client.app.state.ctx.settings,'demo')
    with db.transaction() as tx:
        q2['expiresAt'] = (datetime.now(UTC)-timedelta(minutes=1)).isoformat()
        tx.execute('UPDATE arp_fin_quotes SET doc=? WHERE id=?',(json.dumps(q2),q2['id']))
    assert client.post('/payments/checkout',json={'quoteId':q2['id'],'confirmed':True}).status_code == 409
    assert client.post(f"/payments/{a['id']}/simulate",json={'outcome':'succeeded'}).json()['payment']['status'] == 'succeeded'
    assert client.post(f"/payments/{a['id']}/simulate",json={'outcome':'refunded'}).json()['payment']['refundedCents'] == a['amountCents']


def test_concurrent_reservations_recheck_caps(client, bedroom):
    t = tenancy(client,bedroom['roomId']); q1=quote(client,t,100000);q2=quote(client,t,100000)
    db = PaymentLedger(client.app.state.ctx.settings,'demo')
    def reserve(q):
        try: return db.reserve(t['userId'],q['id'])['id']
        except HTTPException as e: return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(reserve,[q1,q2]))
    assert results.count(409) == 1
    winner = q1 if results[0] != 409 else q2
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(reserve,[winner]*4))) == 1


def test_lifecycle_replay_and_out_of_order(client, bedroom):
    t=tenancy(client,bedroom['roomId']);q=quote(client,t);db=PaymentLedger(client.app.state.ctx.settings,'demo');p=db.reserve(t['userId'],q['id'])
    db.apply_event('evt2',p['id'],'refunded',refunded=p['amountCents'])
    db.apply_event('evt1',p['id'],'succeeded')
    db.apply_event('evt2',p['id'],'disputed')
    assert db.get(p['id'])['status'] == 'refunded'
    assert db.apply_event('evt3',p['id'],'disputed')['status'] == 'disputed'
    assert db.apply_event('evt4',p['id'],'failed')['status'] == 'disputed'


def test_ownership_photos_deletion_and_untrusted_claims(client):
    a={'X-Demo-Session':'a'*40};b={'X-Demo-Session':'b'*40}
    room=client.post('/rooms',headers=a,json={'sample':'nyc-bedroom'}).json();rid=room['room']['id'];lid=room['currentLayout']['id']
    assert client.get(f'/rooms/{rid}',headers=b).status_code == 404
    assert client.get(f'/layouts/{lid}',headers=b).status_code == 404
    assert client.get('/rooms',headers=b).json() == []
    image=Image.new('RGB',(20,20));raw=io.BytesIO();exif=Image.Exif();exif[270]='sensitive metadata';image.save(raw,format='JPEG',exif=exif)
    r=client.post(f'/rooms/{rid}/evidence',headers=a,files={'image':('photo.jpg',raw.getvalue(),'image/jpeg')})
    assert r.status_code == 201,r.text
    photo=r.json()['photo'];assert 'storageKey' not in photo
    data=client.get(f"/evidence/{photo['id']}",headers=a)
    assert not Image.open(io.BytesIO(data.content)).getexif()
    assert client.get(f"/evidence/{photo['id']}",headers=b).status_code == 404
    assert client.delete(f"/evidence/{photo['id']}",headers=b).status_code == 404
    assert client.post(f'/rooms/{rid}/evidence',headers=a,files={'image':('fake.jpg',b'fake','image/jpeg')}).status_code == 422
    body=profile(rid,conditions=[{**issue(),'photoIds':[photo['id']],'source':'photo'}])
    assert client.put(f'/rooms/{rid}/housing-profile',headers=a,json=body).status_code == 200
    assert client.post('/rent/assess',headers=b,json=body).status_code in (404,422)
    assert client.delete(f"/evidence/{photo['id']}",headers=a).status_code == 204
    assert client.get(f"/evidence/{photo['id']}",headers=a).status_code == 404
    assert client.get(f'/rooms/{rid}/housing-profile',headers=a).json()['profile']['conditions'][0]['photoIds'] == []
    assert client.post('/rent/assess',headers=a,json=profile(rid,conditions=[{**issue(),'source':'public_record'}])).status_code == 422
    t=client.post('/payments/test-tenancy',headers=a,json={'roomId':rid}).json()['tenancy']
    q=client.post('/payments/quote',headers=a,json={'tenancyId':t['id'],'purpose':'deposit','amountCents':100,'rentalPeriod':'2026-09'}).json()['quote']
    assert client.post('/payments/checkout',headers=b,json={'quoteId':q['id'],'confirmed':True}).status_code == 404
    p=client.post('/payments/checkout',headers=a,json={'quoteId':q['id'],'confirmed':True}).json()['payment']
    assert client.get(f"/payments/{p['id']}",headers=b).status_code == 404


def test_assistant_cannot_authorize_and_preserves_current(client,bedroom):
    for text in ['I pay $1600 rent. Is it fair? Rats and leak', 'Can I safely send a $500 deposit?']:
        result=client.post('/agent/request',json={'roomId':bedroom['roomId'],'baseLayoutId':bedroom['currentId'],'channel':'app','text':text}).json()
        assert result['layout'] is None and result.get('quote') is None
    assert len(client.get(f"/rooms/{bedroom['roomId']}").json()['layouts']) == 1
    assert client.get('/payments').json()['payments'] == []


def test_replacement_scan_preserves_original_and_links_new_room(client,bedroom):
    original=client.get(f"/rooms/{bedroom['roomId']}").json()['room']
    replacement=client.post('/rooms',json={'dimensions':{'l':4,'w':3,'h':2.7},'supersedesRoomId':original['id']})
    assert replacement.status_code==201
    room=replacement.json()['room']
    assert room['id']!=original['id'] and room['supersedesRoomId']==original['id']
    assert client.get(f"/rooms/{original['id']}").json()['room']['skeleton']==original['skeleton']


def test_divider_door_clearance_and_import_confirmation(client,bedroom):
    imported=client.post('/furniture/manual',json={'name':'Room divider','category':'divider','dims':{'w':1.5,'d':0.35,'h':1.8},'price':75,'deliveryCost':15,'sourceUrl':'https://example.com/divider'}).json()
    assert imported['category']=='divider' and imported['dimensionsConfirmed'] and imported['deliveryCost']==15
    fork=client.post(f"/layouts/{bedroom['currentId']}/fork",json={}).json()
    item={'id':'divider-test','furnitureId':imported['id'],'x':2.6,'z':2.4,'rotation':0,'locked':False}
    response=client.put(f"/layouts/{fork['id']}",json={'items':[item],'source':'editor'})
    assert response.status_code==200
    # Preserve existing designer semantics: doorway violations are visible warnings;
    # bounds/overlap violations block saving.
    assert any(v['rule']=='door_clearance' for v in response.json()['validation']['violations'])
