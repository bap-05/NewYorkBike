$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ArchivePath = Join-Path ([System.IO.Path]::GetTempPath()) 'citibike-deploy.tar.gz'
$Items = @('.github', 'config', 'services', 'frontend', 'shared', 'database', 'scripts', 'deploy', 'docs', 'README.md', 'PROJECT_REPORT.md', 'Yeu_Cau_Web_Seoul_Bike.md', 'pyproject.toml', 'docker-compose.yml', '.dockerignore', 'requirements.txt', 'alembic.ini', '.env.example', '.gitignore')

Get-Command tar.exe -ErrorAction Stop | Out-Null
& tar.exe '--exclude=__pycache__' '--exclude=node_modules' '--exclude=dist' '--exclude=test-results' '--exclude=playwright-report' '--exclude=*.pyc' '--exclude=.env' '--exclude=.env.development' '--exclude=.env.production' '--exclude=*.key' '--exclude=*.pem' -czf $ArchivePath -C $ProjectRoot @Items
if ($LASTEXITCODE -ne 0) { throw 'Could not build deployment archive.' }

$Entries = & tar.exe -tzf $ArchivePath
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect deployment archive.' }
if ($Entries | Where-Object { (($_ -match '(^|/)\.env[^/]*$') -and ($_ -notmatch '(^|/)\.env\.example$')) -or $_ -match '(^|/)(\.env|\.venv|data|__pycache__)(/|$)|\.(key|pem)$' }) {
    throw 'Deployment archive contains excluded paths; do not upload it.'
}
Write-Output "Deployment archive: $ArchivePath"
Write-Output 'Includes code and .env.example; excludes .env, MySQL data, Bronze, virtualenv and SSH keys.'
