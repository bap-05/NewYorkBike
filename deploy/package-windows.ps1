$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ArchivePath = Join-Path ([System.IO.Path]::GetTempPath()) 'citibike-deploy.tar.gz'
$Items = @('.github', 'config', 'ingestion', 'shared', 'database', 'scripts', 'deploy', 'docs', 'README.md', 'requirements.txt', 'alembic.ini', '.env.example', '.gitignore')

Get-Command tar.exe -ErrorAction Stop | Out-Null
& tar.exe '--exclude=__pycache__' '--exclude=*.pyc' '--exclude=.env' '--exclude=*.key' '--exclude=*.pem' -czf $ArchivePath -C $ProjectRoot @Items
if ($LASTEXITCODE -ne 0) { throw 'Could not build deployment archive.' }

$Entries = & tar.exe -tzf $ArchivePath
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect deployment archive.' }
if ($Entries | Where-Object { $_ -match '(^|/)(\.env|\.venv|data|__pycache__)(/|$)|\.(key|pem)$' }) {
    throw 'Deployment archive contains excluded paths; do not upload it.'
}
Write-Output "Deployment archive: $ArchivePath"
Write-Output 'Includes code and .env.example; excludes .env, MySQL data, Bronze, virtualenv and SSH keys.'
