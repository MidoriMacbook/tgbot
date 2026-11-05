param([string]$Path = '.env')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Path)) {
    throw "Файл настроек $Path не найден. Скопируйте .env.example в .env и заполните значения."
}
foreach ($line in Get-Content -LiteralPath $Path -Encoding utf8) {
    if ($line -match '^\s*(#|$)') { continue }
    if ($line -notmatch '^([A-Z_][A-Z0-9_]*)=(.*)$') { throw 'Неверный формат строки настроек' }
    [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim(), 'Process')
}
