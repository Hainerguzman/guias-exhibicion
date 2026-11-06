import urllib.request, urllib.error, json, base64, sys, os, datetime, time

BASE = 'https://prd.appsjamar.com/ecommerce/ambientes/v1'
MAX_RETRIES = 3
RETRY_DELAY = 8  # seconds between retries

def fetch_with_retry(url, retries=MAX_RETRIES):
    """Fetch a URL with retries. Returns (data, True) on success, (error_msg, False) on failure."""
    last_error = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode('utf-8')), True
        except urllib.error.HTTPError as e:
            last_error = f'HTTP {e.code} {e.reason}'
        except urllib.error.URLError as e:
            last_error = f'URLError: {e.reason}'
        except Exception as e:
            last_error = f'{type(e).__name__}: {e}'

        if attempt < retries:
            print(f'    intento {attempt} fallido ({last_error}), reintentando en {RETRY_DELAY}s...')
            time.sleep(RETRY_DELAY)

    return last_error, False

def fetch_all_products(code):
    url = f'{BASE}/ambiente_detail/list/JA/{code}/1'
    data, ok = fetch_with_retry(url)
    if ok:
        return (data if isinstance(data, list) else []), True
    return data, False  # data contains the error message

def fetch_ambientes():
    url = f'{BASE}/ambientes/list/JA'
    data, ok = fetch_with_retry(url)
    if ok:
        return data
    raise Exception(f'No se pudo obtener ambientes: {data}')

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
error_count = 0
success_count = 0

for amb in ambientes:
    code = amb['codigo_ambiente']
    name = amb['nombre_ambiente']

    products, success = fetch_all_products(code)

    if not success:
        had_api_errors = True
        error_count += 1
        existing = existing_guides.get(code)
        if existing:
            guides.append(existing)
            print(f'  [{code}] FALLO ({products}) -> conservando guia existente ({sum(len(v) for v in existing["pisos"].values())} productos)')
        else:
            print(f'  [{code}] FALLO ({products}) -> guia nueva sin datos previos, OMITIDA')
        continue

    if not products:
        print(f'  [{code}] Sin productos, omitiendo')
        continue

    success_count += 1

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
print(f'API calls: {success_count} exitosas, {error_count} fallidas')
if had_api_errors:
    print(f'ADVERTENCIA: {error_count} guias usaron datos de respaldo.')

# --- Push to GitHub ---
new_content = json.dumps(guides, ensure_ascii=False, indent=2)
if new_content.strip() == current_content.strip():
    print('Sin cambios. guides.json ya esta actualizado.')
    sys.exit(0)

new_b64 = base64.b64encode(new_content.encode('utf-8')).decode('ascii')
msg = f'Auto-sync: {len(guides)} guias [{datetime.date.today()}]'
if had_api_errors:
    msg += f' [fallback parcial: {error_count} guias]'
payload = json.dumps({'message': msg, 'content': new_b64, 'sha': sha}).encode('utf-8')
req = urllib.request.Request(api_url, data=payload, method='PUT', headers={
    'Authorization': f'token {token}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github.v3+json'
})
with urllib.request.urlopen(req) as r:
    result = json.loads(r.read().decode('utf-8'))
    print(f'ACTUALIZADO: commit {result["commit"]["sha"][:8]} - {len(guides)} guias, {multi_result} multi-piso')
