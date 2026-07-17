[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$backendRoot = Split-Path -Parent $PSScriptRoot
Push-Location $backendRoot

try {
    $settings = 'config.settings.test'
    python manage.py check --settings=$settings
    python manage.py makemigrations --check --dry-run --settings=$settings
    python manage.py migrate --plan --settings=$settings
    python manage.py test --settings=$settings

    $generatedSchema = Join-Path ([System.IO.Path]::GetTempPath()) 'gahambani-openapi-v1.yaml'
    python manage.py spectacular --validate --file $generatedSchema --settings=$settings
    python -c "import pathlib,yaml; expected=yaml.safe_load(pathlib.Path('openapi-v1.yaml').read_text(encoding='utf-8')); generated=yaml.safe_load(pathlib.Path(r'$generatedSchema').read_text(encoding='utf-8')); assert expected == generated, 'openapi-v1.yaml is not up to date'"

    python -m pip check
    git diff --check
}
finally {
    if ($generatedSchema -and (Test-Path $generatedSchema)) {
        Remove-Item -LiteralPath $generatedSchema
    }
    Pop-Location
}

