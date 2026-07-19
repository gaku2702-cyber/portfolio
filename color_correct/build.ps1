# Build ColorCorrect (PyInstaller onedir) + ZIP for distribution
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> pip install"
python -m pip install -r requirements.txt

Write-Host "==> PyInstaller"
python -m PyInstaller --noconfirm --clean build.spec

$distRoot = Join-Path $PSScriptRoot "dist"
$out = Join-Path $distRoot "ColorCorrect"
$exe = Join-Path $out "ColorCorrect.exe"
if (-not (Test-Path $out)) {
    Write-Error "Build output not found: $out"
}
if (-not (Test-Path $exe)) {
    Write-Error "EXE not found: $exe"
}

Copy-Item -Force (Join-Path $PSScriptRoot "README.md") (Join-Path $out "README.md")
$guide = Join-Path $PSScriptRoot "haifu_guide.txt"
if (Test-Path $guide) {
    Copy-Item -Force $guide (Join-Path $out "haifu_guide.txt")
}
$guideJa = Join-Path $PSScriptRoot "haifu_tebiki.txt"
if (Test-Path $guideJa) {
    Copy-Item -Force $guideJa (Join-Path $out "haifu_tebiki.txt")
}

# 簡易スモーク: 起動して数秒生存するか（GUI のためウィンドウはすぐ閉じる）
Write-Host "==> smoke test (launch EXE)"
$proc = Start-Process -FilePath $exe -PassThru -WindowStyle Minimized
Start-Sleep -Seconds 3
if ($proc.HasExited -and $proc.ExitCode -ne 0) {
    Write-Error "Smoke test failed: EXE exited with code $($proc.ExitCode)"
}
if (-not $proc.HasExited) {
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
}
Write-Host "Smoke OK: EXE launched and stayed alive"

# ZIP（tar 優先。Compress-Archive はファイルロックで失敗しやすい）
$zip = Join-Path $distRoot "ColorCorrect_dist.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Write-Host "==> create ZIP"
$tarOk = $false
try {
    tar -a -c -f $zip -C $distRoot ColorCorrect
    if (Test-Path $zip) { $tarOk = $true }
} catch {
    $tarOk = $false
}
if (-not $tarOk) {
    Start-Sleep -Seconds 2
    Compress-Archive -Path $out -DestinationPath $zip -Force
}

if (-not (Test-Path $zip)) {
    Write-Error "ZIP was not created: $zip"
}

Write-Host ""
Write-Host "DONE"
Write-Host "Folder: $out"
Write-Host "ZIP   : $zip"
Write-Host "Size  : $((Get-Item $zip).Length) bytes"
Write-Host ""
Write-Host "Distribute the whole ColorCorrect folder (exe alone will not work)."
