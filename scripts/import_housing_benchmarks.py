"""Import a manually authorized, attributed HUD/StreetEasy snapshot; never scrape."""
import argparse
import json
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('file', type=Path, help='JSON array with source, zip, mode, label, value, observedAt, retrievedAt, sourceUrl, permittedUse')
args = parser.parse_args()
rows = json.loads(args.file.read_text())
assert isinstance(rows, list)
for row in rows:
    assert row['source'] in ('StreetEasy', 'HUD SAFMR')
    assert row['mode'] in ('demo', 'real') and len(row['zip']) == 5 and row['zip'].isdigit()
    assert row['label'] and row['permittedUse'] and float(row['value']) > 0
    date.fromisoformat(row['observedAt'])
    datetime.fromisoformat(row['retrievedAt'])
    host = urlparse(row['sourceUrl']).hostname or ''
    assert host in ('streeteasy.com', 'www.huduser.gov', 'huduser.gov'), 'Use the original provider URL'
path = Path(__file__).resolve().parents[1] / 'fixtures/housing/benchmarks.json'
path.write_text(json.dumps({'benchmarks': rows}, indent=2) + '\n')
print(f'Imported {len(rows)} context-only records into {path}')
