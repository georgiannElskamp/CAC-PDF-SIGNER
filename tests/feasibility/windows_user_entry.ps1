param([string]$Root,[string]$InputPath,[string]$ReportPath,[string]$PythonPath,[string]$NodePath,[string]$ProfilePath,[string]$ExpectedSid)
$ErrorActionPreference='Stop'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PROBE_INPUT=$InputPath
$env:PROBE_REPORT=$ReportPath
$env:PROBE_NODE=$NodePath
$env:GITHUB_ACTIONS='true'
$env:RUNNER_ENVIRONMENT='github-hosted'
if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne $ExpectedSid){throw 'Wrong account token'}
$env:USERPROFILE=$ProfilePath
$env:APPDATA=Join-Path $ProfilePath 'AppData\Roaming'
$env:LOCALAPPDATA=Join-Path $ProfilePath 'AppData\Local'
New-Item -ItemType Directory -Path $env:APPDATA,$env:LOCALAPPDATA -Force | Out-Null
$env:TEMP=Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
Set-Location -LiteralPath $Root
& $PythonPath -B tests/feasibility/desktop.py --installed
exit $LASTEXITCODE
