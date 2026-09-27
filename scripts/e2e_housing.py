"""Browser acceptance: report pests → compare → divider → reject fee → guarded checkout.
Run locally with zero credentials. --stripe requires configured Supabase login and is manual;
real signed Stripe events and Postgres transaction tests live in test_stripe_postgres.py.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--web',default='http://localhost:5173')
args=parser.parse_args()
out=Path(__file__).resolve().parents[1]/'.context/housing-demo'
out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(args.web)
    page.get_by_role('button',name='Load sample room',exact=False).click()
    dialog=page.get_by_role('dialog',name='Your space & rent')
    dialog.wait_for()
    page.get_by_label('I reviewed the physical area').check()
    page.get_by_role('button',name='Add condition',exact=True).click()
    page.get_by_role('button',name='Compare asking rents',exact=True).click()
    page.get_by_text('Observed comparison difference:',exact=False).wait_for()
    page.screenshot(path=str(out/'comparisons.png'))
    baseline=page.locator('.housing-result').first.inner_text()
    assert 'Insufficient' not in baseline
    assert 'Demo data' in dialog.inner_text()
    page.get_by_role('button',name='Close Your space & rent',exact=True).click()
    page.get_by_role('button',name='Import furniture',exact=True).click()
    page.get_by_label('Item price').fill('75')
    page.get_by_label('Delivery (USD)').fill('15')
    page.get_by_label('I confirmed these dimensions').check()
    page.get_by_role('button',name='Preview in room',exact=True).click()
    page.wait_for_function('() => window.__arpStore.getState().placing !== null')
    # A real palette preview uses the same store placement and shared geometry validator.
    page.evaluate("() => { const s=window.__arpStore.getState(); s.addItem(s.placing.furnitureId,2.6,2.4); s.cancelPlacing(); }")
    page.wait_for_function("() => window.__arpStore.getState().validation.violations.some(v => v.rule === 'door_clearance')")
    page.screenshot(path=str(out/'divider-doorway.png'))
    page.evaluate("() => { const s=window.__arpStore.getState(); s.removeItem(s.selectedId); }")
    page.get_by_role('button',name='rent',exact=True).click()
    page.get_by_role('tab',name='Rent comparisons').click()
    assert page.locator('.housing-result').first.inner_text()==baseline
    page.get_by_role('tab',name='Budget & payments').click()
    page.get_by_role('button',name='Load test tenancy').click()
    page.get_by_label('Payment purpose').select_option('application_fee')
    page.get_by_label('Amount (USD)',exact=True).fill('75')
    page.get_by_role('button',name='Review payment',exact=True).click()
    page.locator('.housing-quote.blocked').wait_for()
    assert page.get_by_role('button',name='Continue to demo checkout').count()==0
    page.screenshot(path=str(out/'fee-blocked.png'))
    page.get_by_label('Payment purpose').select_option('rent_payment')
    page.get_by_label('Amount (USD)',exact=True).fill('1600')
    page.get_by_role('button',name='Review payment',exact=True).click()
    page.get_by_label('I reviewed the recipient').check()
    page.get_by_role('button',name='Continue to demo checkout').click()
    page.get_by_role('heading',name='$1,600.00 · pending').wait_for()
    page.get_by_role('button',name='Simulate successful payment').click()
    page.get_by_role('heading',name='$1,600.00 · succeeded').wait_for()
    assert 'No Stripe transaction' in page.locator('main').inner_text()
    page.screenshot(path=str(out/'demo-payment.png'))
    # Mobile layout: no horizontally clipped forms.
    page.get_by_role('button',name='Back to room').click()
    page.get_by_role('button',name='rent',exact=True).click()
    page.set_viewport_size({'width':390,'height':844})
    dialog=page.get_by_role('dialog')
    assert dialog.evaluate('(d) => d.scrollWidth <= d.clientWidth + 1')
    page.screenshot(path=str(out/'mobile-panel.png'))
    assert not errors, errors
    (out/'results.json').write_text(json.dumps({'ok':True,'mode':'offline demo; no real Stripe call','consoleErrors':errors},indent=2))
    browser.close()
print('Housing demo passed; screenshots in .context/housing-demo/')
