param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')]
    [string]$Repository,
    [string]$Destination = ''
)

$ErrorActionPreference = 'Stop'
# Resolve defaults in the script body: Windows PowerShell may not populate
# $PSScriptRoot while evaluating default parameter expressions.
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $ScriptDirectory = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($ScriptDirectory)) {
        $ScriptFile = $MyInvocation.MyCommand.Path
        if ([string]::IsNullOrWhiteSpace($ScriptFile)) {
            throw 'Cannot locate this script. Run it using powershell -File or supply -Destination explicitly.'
        }
        $ScriptDirectory = Split-Path -Parent $ScriptFile
    }
    $ProjectDirectory = Split-Path -Parent $ScriptDirectory
    $Destination = Join-Path -Path $ProjectDirectory -ChildPath 'backups\bronze'
}
Get-Command gh -ErrorAction Stop | Out-Null
$BackupRoot = [System.IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null

# Only ask for artifact IDs/names; do not retrieve credentials or dump API responses.
$Rows = & gh api --paginate "repos/$Repository/actions/artifacts?per_page=100" --jq '.artifacts[] | select(.expired == false) | [.id, .workflow_run.id, .name] | @tsv'
if ($LASTEXITCODE -ne 0) { throw 'Could not list artifacts. Run gh auth login and check repository access.' }

$Downloaded = 0
foreach ($Row in $Rows) {
    $Parts = $Row -split "`t"
    if ($Parts.Count -ne 3 -or $Parts[0] -notmatch '^\d+$' -or $Parts[1] -notmatch '^\d+$' -or $Parts[2] -notmatch '^citibike-bronze-\d+-\d+$') { continue }
    $ArtifactPath = Join-Path $BackupRoot $Parts[0]
    $MarkerPath = Join-Path $ArtifactPath '.download-complete'
    if (Test-Path -LiteralPath $MarkerPath) { continue }
    New-Item -ItemType Directory -Force -Path $ArtifactPath | Out-Null
    & gh run download $Parts[1] --repo $Repository --name $Parts[2] --dir $ArtifactPath
    if ($LASTEXITCODE -ne 0) { throw 'Artifact download failed. Existing downloads were retained; rerun to retry.' }
    Set-Content -LiteralPath $MarkerPath -Value $Parts[2] -Encoding UTF8
    $Downloaded += 1
}
Write-Output "Downloaded $Downloaded Bronze artifacts to $BackupRoot. Nothing deleted on GitHub or locally."
