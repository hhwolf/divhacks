"""Regenerate financial JSON Schemas from the authoritative Pydantic contracts."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from app.housing_models import HousingProfile, PaymentQuote, PaymentRecord, RentAssessment, Tenancy, QuoteRequest

for name, model in [('housing-profile', HousingProfile), ('payment-quote', PaymentQuote), ('payment-record', PaymentRecord), ('rent-assessment', RentAssessment), ('tenancy', Tenancy), ('quote-request', QuoteRequest)]:
    schema = model.model_json_schema()
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$id'] = f'https://roomplanner.dev/schemas/{name}.schema.json'
    (ROOT / 'packages/contracts/schemas' / f'{name}.schema.json').write_text(json.dumps(schema, indent=2) + '\n')
