"""Generate the readable v1 route inventory from the OpenAPI contract."""
from pathlib import Path
import sys

import yaml


def schema_names(node):
    if not isinstance(node, dict):
        return '-'
    if '$ref' in node:
        return node['$ref'].rsplit('/', 1)[-1]
    names = [schema_names(item) for key in ('oneOf', 'anyOf', 'allOf') for item in node.get(key, [])]
    return ', '.join(name for name in names if name != '-') or node.get('type', '-')


def roles(path, method):
    if path.endswith('/health/'):
        return 'Public'
    if '/auth/' in path:
        public = ('/login/', '/register/', '/refresh/', '/password-reset/', '/password-reset-confirm/')
        return 'Public' if any(item in path for item in public) else 'Authentifié actif'
    if '/profiles/my-patients/' in path:
        return 'Médecin actif'
    if '/profiles/my-doctors/' in path:
        return 'Patient actif'
    if '/profiles/' in path:
        return 'Patient ou médecin actif'
    if '/alerts/' in path and method == 'PATCH':
        return 'Médecin actuellement affecté'
    if '/notifications/' in path:
        return 'Destinataire actif'
    if '/analytics/' in path:
        return 'Patient propriétaire ou médecin affecté'
    if '/monitoring/' in path:
        return 'Patient propriétaire ou médecin affecté'
    if '/medical-records/' in path:
        return 'Patient propriétaire ou médecin affecté'
    if '/alerts/' in path:
        return 'Patient propriétaire ou médecin affecté'
    return 'Authentifié'


def main(source, destination):
    schema = yaml.safe_load(Path(source).read_text(encoding='utf-8'))
    rows = []
    methods = {'get', 'post', 'put', 'patch', 'delete'}
    for path, path_item in schema['paths'].items():
        for method, operation in path_item.items():
            if method not in methods:
                continue
            request = '-'
            request_body = operation.get('requestBody', {}).get('content', {})
            if request_body:
                request = schema_names(next(iter(request_body.values())).get('schema', {}))
            success = next((value for code, value in operation['responses'].items() if str(code).startswith('2')), {})
            content = success.get('content', {})
            output = schema_names(next(iter(content.values())).get('schema', {})) if content else 'binaire/vide'
            parameters = [item.get('name') for item in operation.get('parameters', []) if item.get('in') == 'query']
            pagination = 'Oui' if {'page', 'page_size'} & set(parameters) or 'Paginated' in output or output.startswith('Raw') else 'Non'
            filters = ', '.join(item for item in parameters if item not in {'page', 'page_size'}) or '-'
            codes = ', '.join(str(code) for code in operation['responses'])
            rows.append((method.upper(), path, operation['operationId'], ', '.join(operation.get('tags', [])), roles(path, method.upper()), request, output, pagination, filters, codes, 'Oui'))

    lines = [
        '# Inventaire contractuel API v1', '',
        'Ce fichier est généré depuis `openapi-v1.yaml` par `scripts/generate_api_inventory.py`.',
        'Le nom stable utilisé par Flutter est l’`operationId`. Les noms Django sont placés sous le namespace racine `api-v1` puis sous le namespace applicatif lorsqu’il existe.', '',
        '| Méthode | Chemin | Nom stable | Domaine | Autorisation | Entrée | Sortie | Pagination | Filtres | Codes principaux | OpenAPI |',
        '|---|---|---|---|---|---|---|---|---|---|---|---|',
    ]
    lines.extend('| ' + ' | '.join(str(value).replace('|', '\\|') for value in row) + ' |' for row in rows)
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Path(destination).write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: generate_api_inventory.py openapi-v1.yaml docs/api-v1-routes.md')
    main(sys.argv[1], sys.argv[2])
