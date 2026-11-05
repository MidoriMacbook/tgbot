param([ValidateSet('all','web','bot','notifications')][string]$Component = 'all')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
. "$PSScriptRoot/env.ps1"
$pythonPath = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Сначала создайте .venv и установите requirements.lock' }
switch ($Component) {
    'all' { & $pythonPath run.py }
    'web' { & $pythonPath manage.py serve }
    'bot' { & $pythonPath manage.py runbot }
    'notifications' { & $pythonPath manage.py notify }
}
if ($LASTEXITCODE -ne 0) { throw 'Компонент завершился с ошибкой' }
