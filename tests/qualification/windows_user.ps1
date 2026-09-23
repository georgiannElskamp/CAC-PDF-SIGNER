$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){throw 'Disposable hosted runner required'}
$accountName='CAC Probe '+[char]0xE9
$password=[Guid]::NewGuid().ToString('N')+'aA!7'
$secure=ConvertTo-SecureString $password -AsPlainText -Force
$password=$null
$user=New-LocalUser -Name $accountName -Password $secure -PasswordNeverExpires
try{
$group=Get-LocalGroup -SID 'S-1-5-32-545'
Add-LocalGroupMember -Group $group -Member $user
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class ProbeProfile {
  [DllImport("userenv.dll", CharSet=CharSet.Unicode)]
  public static extern int CreateProfile(string sid, string name, StringBuilder path, uint size);
}
"@
$profileBuffer=[Text.StringBuilder]::new(1024)
$profileResult=[ProbeProfile]::CreateProfile($user.SID.Value,$accountName,$profileBuffer,1024)
$profileEvidence=@{probe='windows-profile-setup';source=$env:GITHUB_SHA;runner=$env:ImageOS;
    status=if($profileResult -eq 0){'passed'}else{'blocked'};unicodeResult=$profileResult;
    profileService=(Get-Service ProfSvc).Status.ToString();stage='CreateProfile before editor launch'}
if($profileResult -ne 0){
    $controlName='CACAsciiControl'
    $control=New-LocalUser -Name $controlName -Password $secure -PasswordNeverExpires
    try{
        $controlBuffer=[Text.StringBuilder]::new(1024)
        $profileEvidence.asciiControlResult=[ProbeProfile]::CreateProfile($control.SID.Value,$controlName,$controlBuffer,1024)
    }finally{Remove-LocalUser -Name $controlName}
}
$profileEvidence | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $env:PROBE_REPORT 'windows-profile-setup.json') -Encoding utf8
if($profileResult -ne 0){throw ('Disposable profile creation failed: '+$profileResult)}
$profilePath=$profileBuffer.ToString()
$credential=[PSCredential]::new(($env:COMPUTERNAME+'\'+$accountName),$secure)
$shared=Join-Path $env:RUNNER_TEMP ('CAC feasibility '+[char]0xE9)
New-Item -ItemType Directory -Path $shared -Force | Out-Null
$report=Join-Path $shared 'report'
New-Item -ItemType Directory -Path $report -Force | Out-Null
$rule=[Security.AccessControl.FileSystemAccessRule]::new($user.SID,'Modify','ContainerInherit,ObjectInherit','None','Allow')
$acl=Get-Acl -LiteralPath $shared
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $shared -AclObject $acl
foreach($readPath in @($env:PROBE_INPUT,$env:GITHUB_WORKSPACE)){
    & icacls $readPath /grant ('*'+$user.SID.Value+':(OI)(CI)RX') /T /Q | Out-Null
    if($LASTEXITCODE -ne 0){throw 'Could not grant fixture access'}
}
$python=(Get-Command python).Source
$node=(Get-Command node).Source
$entry=Join-Path $env:GITHUB_WORKSPACE 'tests\feasibility\windows_user_entry.ps1'
$arguments=@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"'+$entry+'"'),
    '-Root',('"'+$env:GITHUB_WORKSPACE+'"'),'-InputPath',('"'+$env:PROBE_INPUT+'"'),
    '-ProfilePath',('"'+$profilePath+'"'),'-ExpectedSid',('"'+$user.SID.Value+'"'),'-ReportPath',('"'+$report+'"'),'-PythonPath',('"'+$python+'"'),'-NodePath',('"'+$node+'"'))
    $parameters=@{Credential=$credential;LoadUserProfile=$true;WindowStyle='Hidden';
        WorkingDirectory=$shared;ArgumentList=$arguments;PassThru=$true;
        RedirectStandardOutput=(Join-Path $shared 'stdout.txt');RedirectStandardError=(Join-Path $shared 'stderr.txt')}
    $child=Start-Process powershell.exe @parameters
    if(-not $child.WaitForExit(660000)){
        Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue
        throw 'Standard-user probe exceeded its bounded execution time'
    }
    Get-Content -LiteralPath (Join-Path $shared 'stdout.txt')
    Get-Content -LiteralPath (Join-Path $shared 'stderr.txt')
    Copy-Item -Path (Join-Path $report '*') -Destination $env:PROBE_REPORT -Force
    if($child.ExitCode -ne 0){throw ('Standard-user probe failed: '+$child.ExitCode)}
}finally{
    $credential=$null
    $secure=$null
    Remove-LocalUser -Name $accountName
}
