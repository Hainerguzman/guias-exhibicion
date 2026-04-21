import urllib.request, urllib.error, json, base64, sys, os, datetime

BASE = 'https://prd.appsjamar.com/ecommerce/ambientes/v1'

def fetch_all_products(code):
    """Fetch ALL products for a guide via the /1 endpoint.
    The API returns all products regardless of piso in this call.
    Each product has a 'piso' field indicating its actual floor.
    Returns (list, True) on success, (None, False) on any error."""
    url = f'{BASE}/ambiente_detail/list/JA/{code}/1'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode('utf-8'))
            return (data if isinstance(data, list) else []), True
    except Exception:
        return None, False

def fetch_ambientes():
    url = f'{BASE}/ambientes/list/JA'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))

# --- Load existing guides.json from GitHub (fallback on API failure) ---
token = os.environ['GITHUB_TOKEN']
api_url = 'https://api.github.com/repos/Hainerguzman/guias-exhibicion/contents/guides.json'
req = urllib.request.Request(api_url, headers={
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
})
with urllib.request.urlopen(req) as r:
    info = json.loads(r.read().decode('utf-8'))
    sha = info['sha']
    current_content = base64.b64decode(info['content'].replace('\n', '')).decode('utf-8')

existing_guides = {g['code']: g for g in json.loads(current_content)}
multi_existing = sum(1 for g in existing_guides.values() if len(g.get('pisos', {})) > 1)
print(f'Existing: {len(existing_guides)} guides, {multi_existing} with 2+ pisos')

# --- Fetch active environments ---
try:
    ambientes = [a for a in fetch_ambientes() if a.get('estado') == 'A']
except Exception as e:
    print(f'ERROR fetching ambientes: {e}')
    sys.exit(1)

print(f'Active environments from API: {len(ambientes)}')
if not ambientes:
    print('ERROR: No environments returned.')
    sys.exit(1)

# --- Build guides: single API call per guide, group by product's piso field ---
guides = []
had_api_errors = False

for amb in ambientes:
    code = amb['codigo_ambiente']
    name = amb['nombre_ambiente']

    products, success = fetch_all_products(code)

    if not success:
        # API completely failed - preserve entire existing guide if we have it
        had_api_errors = True
        existing = existing_guides.get(code)
        if existing:
            guides.append(existing)
            print(f'  [{code}] API error -> keeping entire existing guide ({sum(len(v) for v in existing["pisos"].values())} products)')
        else:
            print(f'  [{code}] API error -> no existing data, skipping')
        continue

    if not products:
        print(f'  [{code}] No products returned, skipping')
        continue

    # Group active products by their 'piso' field
    pisos = {}
    for p in products:
        if p.get('estado') != 'A':
            continue
        piso_key = str(p.get('piso', 1))
        item = {
            'c': p['producto'].split(' - ')[0].strip(),
            'n': p.get('name') or p['producto'].split(' - ', 1)[-1].strip(),
            'q': p.get('can', 0),
            'o': p.get('can_oc', 0),
            'img': p.get('image', '')
        }
        if piso_key not in pisos:
            pisos[piso_key] = []
        pisos[piso_key].append(item)

    if pisos:
        guides.append({'code': code, 'name': name, 'pisos': pisos})

multi_result = sum(1 for g in guides if len(g['pisos']) > 1)
print(f'Result: {len(guides)} guides, {multi_result} with 2+ pisos')
if had_api_errors:
    print('NOTE: Some guides had API errors - existing data was preserved for those.')

# --- Push to GitHub ---
new_content = json.dumps(guides, ensure_ascii=False, indent=2)
if new_content.strip() == current_content.strip():
    print('No changes. guides.json is already up to date.')
    sys.exit(0)

new_b64 = base64.b64encode(new_content.encode('utf-8')).decode('ascii')
msg = f'Auto-sync: {len(guides)} guias [{datetime.date.today()}]'
if had_api_errors:
    msg += ' [fallback parcial]'
payload = json.dumps({'message': msg, 'content': new_b64, 'sha': sha}).encode('utf-8')
req = urllib.request.Request(api_url, data=payload, method='PUT', headers={
    'Authorization': f'token {token}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github.v3+json'
})
with urllib.request.urlopen(req) as r:
    result = json.loads(r.read().decode('utf-8'))
    print(f'UPDATED: commit {result["commit"]["sha"][:8]} - {len(guides)} guias, {multi_result} multi-piso')
