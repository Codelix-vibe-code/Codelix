param(
    [string]$PythonExe = "C:\Users\Koko\AppData\Local\Programs\Python\Python312\python.exe",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).Path
$version = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($version -ne "3.12") { throw "Vybelix nécessite Python 3.12 pour ce build; détecté : $version" }

$tools = Join-Path $env:TEMP "vybelix-build-tools"
if (-not (Test-Path (Join-Path $tools "PyInstaller\__main__.py"))) {
    & $python -m pip install --target $tools "pyinstaller==6.22.3"
    if ($LASTEXITCODE -ne 0) { throw "Installation temporaire de PyInstaller échouée." }
}
$webviewTools = Join-Path $env:TEMP "vybelix-webview-runtime"
if (-not (Test-Path (Join-Path $webviewTools "webview\__init__.py"))) {
    & $python -m pip install --target $webviewTools "pywebview==6.2.1"
    if ($LASTEXITCODE -ne 0) { throw "Installation temporaire de pywebview échouée." }
}

$buildRoot = Join-Path $repoRoot "build\windows"
$distRoot = Join-Path $buildRoot "dist-desktop"
$workRoot = Join-Path $buildRoot "work"
$specRoot = Join-Path $buildRoot "spec"
$env:PYTHONPATH = "$tools;$webviewTools;$(Join-Path $repoRoot 'src')"
$env:PYTHONNOUSERSITE = "1"

& $python -m PyInstaller `
    --noconfirm --clean --onedir --windowed `
    --name Vybelix `
    --icon (Join-Path $PSScriptRoot "vybelix.ico") `
    --distpath $distRoot `
    --workpath $workRoot `
    --specpath $specRoot `
    --paths (Join-Path $repoRoot "src") `
    --add-data "$(Join-Path $repoRoot 'src\vybelix\ui_assets');vybelix\ui_assets" `
    --add-data "$(Join-Path $repoRoot 'config.example.toml');vybelix" `
    --hidden-import tkinter.filedialog `
    --hidden-import tkinter.messagebox `
    --hidden-import webview.platforms.winforms `
    --hidden-import clr `
    (Join-Path $PSScriptRoot "launcher.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a échoué." }

$exe = Join-Path $distRoot "Vybelix\Vybelix.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Le binaire Vybelix.exe n’a pas été produit." }
Write-Host "Application construite : $exe"

if (-not $SkipInstaller) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        $isccPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $isccPath) { throw "Vybelix.exe est construit. Inno Setup 6 est requis pour créer l’installateur .exe." }
        $isccPath = (Resolve-Path -LiteralPath $isccPath).Path
    } else { $isccPath = $iscc.Source }
    & $isccPath (Join-Path $PSScriptRoot "vybelix.iss")
    if ($LASTEXITCODE -ne 0) { throw "Compilation Inno Setup échouée." }
}
