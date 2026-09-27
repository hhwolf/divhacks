"""Phone editor and optional Expo web form regression checks.
Usage: python scripts/e2e_phone.py --web URL --api URL [--native EXPO_WEB_URL]
Expo web is only a QA harness; install react-native-web locally without saving.
"""
import argparse
import json
import pathlib
import urllib.request
import uuid
from playwright.sync_api import sync_playwright, expect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--web', default='http://localhost:5173')
    ap.add_argument('--api', default='http://localhost:8000')
    ap.add_argument('--native')
    ap.add_argument('--native-only', action='store_true')
    ap.add_argument('--out', default='.context/phone-qa')
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    session = uuid.uuid4().hex
    req = urllib.request.Request(a.api + '/rooms', method='POST', data=json.dumps({'sample': 'l-shaped', 'spaceTypes': ['bedroom'], 'elements': [{'id':'bed', 'label':'Bed', 'furnitureIds':['bed_double']}]}).encode(), headers={'Content-Type': 'application/json', 'X-Demo-Session': session})
    with urllib.request.urlopen(req, timeout=30) as f:
        room = json.load(f)

    req = urllib.request.Request(a.api + '/rooms', method='POST', data=json.dumps({'skeleton':room['room']['skeleton'], 'seed':False}).encode(), headers={'Content-Type':'application/json','X-Demo-Session':session})
    with urllib.request.urlopen(req, timeout=30) as f:
        empty_room = json.load(f)

    def on_screen(locator, w, h, minimum=0):
        box = locator.bounding_box()
        assert box and box['x'] >= -1 and box['y'] >= -1, box
        assert box['x'] + box['width'] <= w + 1 and box['y'] + box['height'] <= h + 1, box
        assert box['width'] >= minimum and box['height'] >= minimum, box
        return box

    with sync_playwright() as p:
        for engine in ([] if a.native_only else [p.chromium, p.webkit]):
            browser = engine.launch(**({'args': ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']} if engine == p.chromium else {}))
            for w, h in [(750,393), (568,320), (320,568), (390,844), (852,393)]:
                pg = browser.new_page(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True, device_scale_factor=2)
                pg.add_init_script('localStorage.setItem("arp-demo-session",' + json.dumps(session) + ');')
                pg.goto(a.web + '/layout/' + room['currentLayout']['id'] + '?embedded=1', wait_until='networkidle')
                expect(pg.get_by_role('button', name='Open furniture inventory')).to_be_visible()
                assert 'theme-teal' in pg.locator('.editor').get_attribute('class')
                controls = pg.locator('.top-left .sq:visible, .top-right .sq:visible, .bottom-center .sq:visible, .palette-toggle, .request-fab')
                boxes = [on_screen(c,w,h,44) for c in controls.all()]
                for i,b in enumerate(boxes):
                    for c in boxes[i+1:]:
                        assert not (b['x'] < c['x']+c['width']-1 and c['x'] < b['x']+b['width']-1 and b['y'] < c['y']+c['height']-1 and c['y'] < b['y']+b['height']-1), (b,c)
                pg.screenshot(path=str(out / f'editor-{engine.name}-{w}.png'))
                pg.get_by_role('button', name='Open furniture inventory').click()
                on_screen(pg.locator('.palette'),w,h)
                on_screen(pg.get_by_role('button',name='Close furniture inventory'),w,h,44)
                tile = pg.locator('.palette .tile').nth(1)
                box = on_screen(tile,w,h,72)
                assert box['width'] >= 80
                assert float(tile.locator('.tile-name').evaluate('(e)=>getComputedStyle(e).fontSize').removesuffix('px')) >= 11
                pg.screenshot(path=str(out / f'inventory-{engine.name}-{w}.png'))
                last = pg.locator('.palette .tile').last
                last.scroll_into_view_if_needed()
                on_screen(last,w,h,72)
                pg.get_by_role('button',name='Categories',exact=True).click()
                pg.get_by_role('button',name='Dividers',exact=True).click()
                assert pg.locator('.palette .tile').count() >= 2
                pg.locator('.palette .tile').nth(1).click()
                expect(pg.locator('.palette')).to_be_hidden()
                pg.get_by_role('button',name='Open furniture inventory').click()
                pg.get_by_role('button',name='Search',exact=True).click()
                pg.get_by_placeholder('Search furniture…').fill('does not exist')
                assert pg.locator('.palette .tile').count() == 1
                pg.get_by_role('button',name='Close furniture inventory').click()
                pg.get_by_role('button',name='Room goals').click()
                on_screen(pg.locator('.needs'),w,h)
                pg.get_by_role('button',name='Ask',exact=True).click()
                on_screen(pg.locator('.request-bar'),w,h)
                for mode in pg.locator('.assist-modes button').all():
                    on_screen(mode,w,h,44)
                pg.locator('.request-bar').get_by_role('button',name='Close',exact=True).click()
                pg.get_by_role('button',name='Overlays',exact=True).click()
                on_screen(pg.locator('[data-testid=overlay-popover]'),w,h)
                pg.get_by_role('button',name='Overlays',exact=True).click()
                pg.goto(a.web + '/layout/' + empty_room['currentLayout']['id'] + '?embedded=1', wait_until='networkidle')
                on_screen(pg.locator('.furnish-card'),w,h)
                close=pg.get_by_role('button',name='Close furnishing ideas')
                on_screen(close,w,h,44)
                close.click()
                expect(pg.locator('.furnish-card')).to_be_hidden()
                pg.screenshot(path=str(out / f'empty-scanned-room-{engine.name}-{w}.png'))
                print(f'PASS {engine.name} editor {w}x{h}: controls, inventory, scroll, categories, search, goals, green background', flush=True)
                pg.close()
            browser.close()

        if a.native:
            browser = p.chromium.launch()
            for w,h in [(320,568),(390,844),(430,932)]:
                pg = browser.new_page(viewport={'width':w,'height':h},is_mobile=True,has_touch=True,device_scale_factor=2)
                settings={'units':'imperial','apiUrl':a.api,'webUrl':a.web,'onboarded':True}
                pg.add_init_script('localStorage.setItem("arp.settings.v1",'+json.dumps(json.dumps(settings))+');')
                created=[]
                def proxy(route):
                    if route.request.method == 'OPTIONS':
                        route.fulfill(status=204,headers={'access-control-allow-origin':'*','access-control-allow-headers':'*','access-control-allow-methods':'*'})
                    else:
                        response=route.fetch()
                        if route.request.method == 'POST' and route.request.url == a.api+'/rooms':
                            created.append((route.request.post_data_json,response.json()))
                        route.fulfill(response=response,headers={**response.headers,'access-control-allow-origin':'*'})
                pg.route(a.api+'/**',proxy)
                pg.goto(a.native+'/?insets=59,0,34,0',wait_until='networkidle')
                pg.get_by_role('button',name='Load sample room',exact=True).click()
                expect(pg.get_by_text('What kind of space is this?',exact=True)).to_be_visible()
                assert not created, 'Room created before goals were confirmed'
                expect(pg.get_by_text('256 sq ft',exact=False)).to_be_visible()
                pg.get_by_role('checkbox',name='Bedroom',exact=True).click()
                continue_button = pg.get_by_role('button',name='Continue with 1 selected')
                on_screen(continue_button,w,h,44)
                pg.screenshot(path=str(out / f'goals-native-{w}.png'))
                continue_button.click()
                expect(pg.get_by_text('What does this room need?',exact=True)).to_be_visible()
                custom=pg.get_by_role('textbox',name='Add your own element')
                custom.fill('A long reading nook with shelves and warm lighting')
                pg.get_by_role('button',name='Add',exact=True).click()
                pg.get_by_role('checkbox',name='A long reading nook with shelves and warm lighting').scroll_into_view_if_needed()
                create=pg.get_by_role('button',name='Create sample room')
                on_screen(create,w,h,44)
                pg.screenshot(path=str(out / f'goals-details-native-{w}.png'))
                create.click()
                pg.wait_for_url('**/editor/**')
                assert len(created)==1
                payload,result=created[0]
                assert payload['sample']=='l-shaped' and payload['spaceTypes']==['bedroom']
                assert any(e.get('custom') for e in payload['elements'])
                assert len(result['currentLayout']['items']) > 0, 'Sample furniture lost during goals flow'
                print(f'PASS native sample goals {w}x{h}: no early creation, measured area, selection, custom goal, one creation with furniture',flush=True)
                pg.close()
            for flow in ['welcome', 'manual', 'scan']:
                pg = browser.new_page(viewport={'width':320,'height':568},is_mobile=True,has_touch=True)
                settings={'units':'metric','apiUrl':a.api,'webUrl':a.web,'onboarded':flow!='welcome'}
                pg.add_init_script('localStorage.setItem("arp.settings.v1",'+json.dumps(json.dumps(settings))+');')
                pg.route(a.api+'/**',proxy)
                pg.goto(a.native+('/scan' if flow=='scan' else '/')+'?insets=20,0,0,0',wait_until='networkidle')
                if flow == 'welcome':
                    for _ in range(2):
                        pg.get_by_role('button',name='Next',exact=True).click()
                        pg.wait_for_timeout(350)
                    pg.get_by_role('button',name='Try the sample room',exact=True).click()
                elif flow == 'manual':
                    pg.get_by_role('button',name='Enter dimensions',exact=True).click()
                    pg.get_by_role('textbox',name='Length (m)').fill('4')
                    pg.get_by_role('textbox',name='Width (m)').fill('3')
                    button=pg.get_by_role('button',name='Continue',exact=True)
                    button.scroll_into_view_if_needed()
                    on_screen(button,320,568,44)
                    pg.screenshot(path=str(out/'dimensions-native-320.png'))
                    button.click()
                else:
                    pg.get_by_role('button',name='Load sample room',exact=True).click()
                expect(pg.get_by_text('What kind of space is this?',exact=True)).to_be_visible()
                print(f'PASS native {flow} entry opens goals',flush=True)
                pg.close()
            browser.close()

if __name__ == '__main__':
    main()
