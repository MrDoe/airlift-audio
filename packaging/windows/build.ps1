# Build the Windows installer: PyInstaller one-folder + Inno Setup.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$Version = $env:VERSION
if (-not $Version) {
    $Pyproject = Get-Content (Join-Path $Root "pyproject.toml") -Raw
    if ($Pyproject -match 'version = "([^"]+)"') {
        $Version = $Matches[1]
    }
}
if (-not $Version) { throw "Could not determine the app version" }

python -m PyInstaller packaging\airlift.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) {
    choco install innosetup -y --no-progress
}
& $Iscc "/DMyAppVersion=$Version" "packaging\windows\airlift.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

Write-Host "Installer written to dist\Airlift-Audio-Setup-*.exe"
