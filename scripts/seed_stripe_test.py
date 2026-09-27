"""Create a Connect test account. Never accepts a live key; prints only its account ID."""
import os
import stripe
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('STRIPE_SECRET_KEY', '')
if not key.startswith('sk_test_'):
    raise SystemExit('Set STRIPE_SECRET_KEY to a test secret key.')
stripe.api_key = key
account = stripe.Account.create(type='express', country='US', business_type='individual',
    capabilities={'card_payments': {'requested': True}, 'transfers': {'requested': True}},
    business_profile={'product_description': 'Fictional rental payment test; no live collections'},
    metadata={'arp_fixture': 'test_landlord'}, idempotency_key='arp-fictional-test-landlord-v1')
print('STRIPE_CONNECTED_ACCOUNT=' + account.id)
print('Complete TEST account onboarding in the Stripe dashboard before Checkout; never use real personal data in fixtures.')
