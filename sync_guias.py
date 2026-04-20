import urllib.request, urllib.error, json, base64, sys, os, time

BASE = 'https://prd.appsjamar.com/ecommerce/ambientes/v1'

def fetch(url, retries=3, delay=5):
    """Fetch JSON from URL. Returns [] on empty/404. Raises on persistent 503."""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode('utf-8'))
                return data if isinstance(data, list) else []
        except urllib.error.HTTPError as e:
            if e.code == 503:
                last_err = e
                print(f'  503 on {url} (attempt {attempt+1}/{retries}), retrying in {delay}s...')
                time.sleep(delay)
            elif e.code == 404:
                return []
            else:
                print(f'  HTTP {e.code} fetching {url}')
                return []
        except Exception as e:
            print(f'  Error fetching {url}: {e}')
            return []
    print(f'  Persistent 503 on {url} after {retries} retries.')
    raise RuntimeError(f'503_persistent:{url}')

# --- Load existing guides.json to fall back to on errors ---
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
print(f'Guias existentes en repo: {len(existing_guides)}')

# --- Fetch active environments ---
ambientes = [a for a in fetch(f'{BASE}/ambientes/list/JA') if a.get('estado') == 'A']
print(f'Ambientes activos: {len(ambientes)}')
if not ambientes:
    print('ERROR: No se obtuvieron ambientes.')
    sys.exit(1)

# --- Build guides ---
guides = []
had_503 = False

for amb in ambientes:
    code = amb['codigo_ambiente']
    name = amb['nombre_ambiente']
    pisos = {}
    for piso_num in range(1, 11):
        try:
            products = fetch(f'{BASE}/ambiente_detail/list/JA/{code}/{piso_num}')
        except RuntimeError as e:
            if '503_persistent' in str(e):
                print(f'  [{code}] piso {piso_num}: 503 persistente — conservando datos anteriores.')
                had_503 = True
                # Fall back to existing data for this guide
                if code in existing_guides:
                    pisos = existing_guides[code].get('pisos', {})
                break
            raise
        if not products:
            break
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
            pisos[str(piso_num)] = items

    if pisos:
        guides.append({'code': code, 'name': name, 'pisos': pisos})

print(f'Guias con productos: {len(guides)}')
if had_503:
    print('AVISO: Algunos pisos tuvieron 503 persistente — se conservaron datos anteriores para esos pisos.')

# --- Push to GitHub ---
new_content = json.dumps(guides, ensure_ascii=False, indent=2)
if new_content.strip() == current_content.strip():
    print('Sin cambios. guides.json ya esta al dia.')
    sys.exit(0)

new_b64 = base64.b64encode(new_content.encode('utf-8')).decode('ascii')
import datetime
payload = json.dumps({
    'message': f'Auto-sync: {len(guides)} guias [{datetime.date.today()}]{"  [503 fallback]" if had_503 else ""}',
    'content': new_b64,
    'sha': sha
}).encode('utf-8')
req = urllib.request.Request(api_url, data=payload, method='PUT', headers={
    'Authorization': f'token {token}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github.v3+json'
})
with urllib.request.urlopen(req) as r:
    result = json.loads(r.read().decode('utf-8'))
    print(f'ACTUALIZADO: commit {result["commit"]["sha"][:8]} - {len(guides)} guias')
