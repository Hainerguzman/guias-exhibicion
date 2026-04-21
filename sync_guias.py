import urllib.request, urllib.error, json, base64, sys, os, datetime

BASE = 'https://prd.appsjamar.com/ecommerce/ambientes/v1'

def fetch_piso(code, piso_num):
    """Fetch products for one piso. Returns (list, True) on success, (None, False) on any error."""
    url = f'{BASE}/ambiente_detail/list/JA/{code}/{piso_num}'
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

# --- Load existing guides.json from GitHub (source of truth for piso structure) ---
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

# --- Build guides, preserving piso structure on API errors ---
guides = []
had_api_errors = False

for amb in ambientes:
    code = amb['codigo_ambiente']
    name = amb['nombre_ambiente']
    # Use existing piso structure as safety net
    existing_pisos = existing_guides.get(code, {}).get('pisos', {})
    pisos = {}

    for piso_num in range(1, 11):
        piso_key = str(piso_num)
        products, success = fetch_piso(code, piso_num)

        if success:
            if not products:
                # API returned 200 empty list = genuine end of pisos
                break
            # Got real data — build items
            items = [
                {
                    'c': p['producto'].split(' - ')[0].strip(),
                    'n': p.get('name') or p['producto'].split(' - ', 1)[-1].strip(),
                    'q': p.get('can', 0),
                    'o': p.get('can_oc', 0),
                    'img': p.get('image', '')
                }
                for p in products if p.get('estado') == 'A'
            ]
            if items:
                pisos[piso_key] = items
        else:
            # API error (503 or other) — preserve existing piso if it existed
            had_api_errors = True
            if piso_key in existing_pisos:
                pisos[piso_key] = existing_pisos[piso_key]
                print(f'  [{code}] piso {piso_num}: API error → keeping existing {len(existing_pisos[piso_key])} items')
                continue  # keep checking higher pisos
            else:
                # This piso never existed → stop
                break

    if pisos:
        guides.append({'code': code, 'name': name, 'pisos': pisos})

multi_result = sum(1 for g in guides if len(g['pisos']) > 1)
print(f'Result: {len(guides)} guides, {multi_result} with 2+ pisos')
if had_api_errors:
    print('NOTE: Some pisos had API errors ℔ existing data was preserved for those pisos.')

# --- Push to GitHub ---
new_content = json.dumps(guides, ensure_ascii=False, indent=2)
if new_content.strip() == current_content.strip():
    print('No changes. guides.json is already up to date.')
    sys.exit(0)

new_b64 = base64.b64encode(new_content.encode('utf-8')).decode('ascii')
msg = f'Auto-sync: {len(guides)} guias [{datetime.date.today()}]'
if had_api_errors:
    msg += ' [piso fallback activo]'
payload = json.dumps({'message': msg, 'content': new_b64, 'sha': sha}).encode('utf-8')
req = urllib.request.Request(api_url, data=payload, method='PUT', headers={
    'Authorization': f'token {token}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github.v3+json'
})
with urllib.request.urlopen(req) as r:
    result = json.loads(r.read().decode('utf-8'))
    print(f'UPDATED: commit {result["commit"]["sha"][:8]} — {len(guides)} guias, {multi_result} multi-piso')
