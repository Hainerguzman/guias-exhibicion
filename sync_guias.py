import urllib.request, json, base64, sys, os

BASE = 'https://prd.appsjamar.com/ecommerce/ambientes/v1'

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f'Error fetching {url}: {e}')
        return []

ambientes = [a for a in fetch(f'{BASE}/ambientes/list/JA') if a.get('estado') == 'A']
print(f'Ambientes activos: {len(ambientes)}')
if not ambientes:
    print('ERROR: No se obtuvieron ambientes.')
    sys.exit(1)

guides = []
for amb in ambientes:
    code = amb['codigo_ambiente']
    name = amb['nombre_ambiente']
    pisos = {}
    for piso_num in range(1, 11):
        products = fetch(f'{BASE}/ambiente_detail/list/JA/{code}/{piso_num}')
        if not products:
            break
        items = [
            {
                'c': p['producto'].split(' - ')[0].strip(),
                'n': p.get('name', p['producto'].split(' - ', 1)[-1].strip()),
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

token = os.environ['GITHUB_TOKEN']
api_url = 'https://api.github.com/repos/Hainerguzman/guias-exhibicion/contents/guides.json'
req = urllib.request.Request(api_url, headers={
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
})
with urllib.request.urlopen(req) as r:
    info = json.loads(r.read().decode('utf-8'))
    sha = info['sha']
    current_content = base64.b64decode(info['content'].replace('
', '')).decode('utf-8')

new_content = json.dumps(guides, ensure_ascii=False, indent=2)
if new_content.strip() == current_content.strip():
    print('Sin cambios. guides.json ya esta al dia.')
    sys.exit(0)

new_b64 = base64.b64encode(new_content.encode('utf-8')).decode('ascii')
import datetime
payload = json.dumps({
    'message': f'Auto-sync: {len(guides)} guias [{datetime.date.today()}]',
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
    print(f'ACTUALIZADO: commit {result["commit"]["sha"][:8]} — {len(guides)} guias')
