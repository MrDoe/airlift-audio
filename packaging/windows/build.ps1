# Build the Windows installer: PyInstaller one-folder + Inno Setup.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

python -m PyInstaller packaging\airlift.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) {
    choco install innosetup -y --no-progress
}
& $Iscc "packaging\windows\airlift.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

Write-Host "Installer written to dist\Airlift-Audio-Setup-*.exe"
