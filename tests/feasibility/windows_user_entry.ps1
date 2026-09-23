param([string]$Root,[string]$InputPath,[string]$ReportPath,[string]$PythonPath,[string]$NodePath)
$ErrorActionPreference='Stop'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PROBE_INPUT=$InputPath
$env:PROBE_REPORT=$ReportPath
$env:PROBE_NODE=$NodePath
$env:GITHUB_ACTIONS='true'
$env:RUNNER_ENVIRONMENT='github-hosted'
$env:USERPROFILE=[Environment]::GetFolderPath('UserProfile')
$env:APPDATA=[Environment]::GetFolderPath('ApplicationData')
$env:LOCALAPPDATA=[Environment]::GetFolderPath('LocalApplicationData')
$env:TEMP=Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
Set-Location -LiteralPath $Root
& $PythonPath -B tests/feasibility/desktop.py --installed
exit $LASTEXITCODE
