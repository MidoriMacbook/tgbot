param([ValidateSet('web','bot','notifications')][string]$Component = 'web')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
. "$PSScriptRoot/env.ps1"
$pythonPath = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Сначала создайте .venv и установите requirements.lock' }
switch ($Component) {
    'web' { & $pythonPath manage.py runserver 127.0.0.1:8000 --noreload }
    'bot' { & $pythonPath manage.py runbot }
    'notifications' { & $pythonPath manage.py notify }
}
if ($LASTEXITCODE -ne 0) { throw 'Компонент завершился с ошибкой' }
