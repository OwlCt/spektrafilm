# Windows x64 portable folder, zip, and Inno Setup installer.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Log($Message) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message)
}

$Work = Join-Path $Root "dist\work"
$App = Join-Path $Root "dist\Spektrafilm"
New-Item -ItemType Directory -Force -Path $Work, $App | Out-Null

Log "downloading CPython 3.13"
$headers = @{ "User-Agent" = "spektrafilm-build" }
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest" -Headers $headers
$asset = $release.assets | Where-Object { $_.name -match '^cpython-3\.13\.[0-9]+\+[0-9]+-x86_64-pc-windows-msvc-install_only_stripped\.tar\.gz$' } | Select-Object -First 1
if (-not $asset) { throw "python-build-standalone asset not found" }
$archive = Join-Path $Work "python.tar.gz"
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archive -Headers $headers
tar -xzf $archive -C $Work
$Runtime = Join-Path $App "runtime"
if (Test-Path $Runtime) { Remove-Item -Recurse -Force $Runtime }
Move-Item (Join-Path $Work "python") $Runtime
$Python = Join-Path $Runtime "python.exe"

Log "installing spektrafilm"
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $Python -m pip install --no-cache-dir $Root pillow
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Log "drawing icon"
& $Python (Join-Path $Root "packaging\macos\make_icon.py") `
    --iconset (Join-Path $Work "unused.iconset") `
    --png (Join-Path $Work "app_icon.png") `
    --ico (Join-Path $App "spektrafilm.ico")
if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }

Log "pruning unused Qt modules"
& $Python -c @"
import os, pathlib, shutil
import PySide6
root = pathlib.Path(PySide6.__file__).resolve().parent
needles = ('QtWebEngine','QtWebView','QtPdf','Qt3D','QtQuick3D','QtMultimedia','QtDesigner')
removed = 0
for dirpath, dirnames, filenames in os.walk(root, topdown=False):
    for name in filenames + dirnames:
        if not any(needle in name for needle in needles):
            continue
        path = pathlib.Path(dirpath) / name
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        removed += 1
print(f'removed {removed} PySide6 paths')
"@
if ($LASTEXITCODE -ne 0) { throw "prune failed" }

Copy-Item (Join-Path $Root "packaging\macos\smoke_check.py") (Join-Path $App "smoke_check.py")
Copy-Item (Join-Path $Root "packaging\windows\launch.pyw") (Join-Path $App "launch.pyw")
Copy-Item (Join-Path $Root "packaging\windows\Spektrafilm.cmd") (Join-Path $App "Spektrafilm.cmd")
Copy-Item (Join-Path $Root "packaging\windows\Spektrafilm.vbs") (Join-Path $App "Spektrafilm.vbs")

Log "offscreen smoke test"
$env:QT_QPA_PLATFORM = "offscreen"
$env:NUMBA_NUM_THREADS = "1"
$env:PYTHONNOUSERSITE = "1"
$env:QT_API = "pyside6"
$env:SPEKTRAFILM_CONFIG_DIR = Join-Path $env:TEMP "spektrafilm-smoke"
cmd /c "`"$App\Spektrafilm.cmd`" --smoke"
if ($LASTEXITCODE -ne 0) { throw "smoke test failed with exit $LASTEXITCODE" }

Log "zipping portable app"
$Zip = Join-Path $Root "dist\Spektrafilm-windows-x64.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
tar -a -c -f $Zip -C (Join-Path $Root "dist") Spektrafilm
Get-Item $Zip | Format-List FullName, Length

Log "building Inno Setup installer"
$Setup = Join-Path $Work "innosetup.exe"
Invoke-WebRequest -Uri "https://github.com/jrsoftware/issrc/releases/download/is-6_4_1/innosetup-6.4.1.exe" -OutFile $Setup -Headers $headers
Start-Process -FilePath $Setup -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/SP-" -Wait
$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { $Iscc = "$env:ProgramFiles\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $Iscc)) { throw "ISCC.exe not found" }
& $Iscc (Join-Path $Root "packaging\windows\spektrafilm.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Get-ChildItem (Join-Path $Root "dist") -Filter "Spektrafilm-windows-x64-setup.exe" | Format-List FullName, Length
Log "Windows bundle ready"
