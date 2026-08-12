param(
  [string]$BaseUrl = "http://127.0.0.1:8080",
  [int]$WaitMs = 1800,
  [int]$LongWaitMs = 2800
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "===== MESFlow USER GUIDE VIDEO ====="
Write-Host "Base URL: $BaseUrl"

try {
  $r = Invoke-WebRequest "$BaseUrl/api/system/version" -UseBasicParsing -TimeoutSec 10
  Write-Host "MESFlow reachable: HTTP $($r.StatusCode)"
} catch {
  throw "MESFlow chưa truy cập được tại $BaseUrl. Hãy start/deploy app trước."
}

if (-not (Test-Path "node_modules\@playwright\test")) {
  Write-Host "Installing npm dependencies..."
  npm install
}

Write-Host "Installing Chromium if needed..."
npx playwright install chromium

$env:MESFLOW_BASE_URL = $BaseUrl
$env:MESFLOW_TUTORIAL_WAIT_MS = "$WaitMs"
$env:MESFLOW_TUTORIAL_LONG_WAIT_MS = "$LongWaitMs"

npm run video:tutorial
if ($LASTEXITCODE -ne 0) { throw "Playwright tutorial failed." }

$videos = Get-ChildItem "test-results\tutorial" -Recurse -Filter *.webm | Sort-Object LastWriteTime -Descending
if (-not $videos) { throw "Không tìm thấy video .webm." }

$out = Join-Path $root "tutorial-output"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$webm = Join-Path $out "MESFlow_User_Guide.webm"
Copy-Item $videos[0].FullName $webm -Force
Write-Host ""
Write-Host "VIDEO READY:"
Write-Host $webm

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpeg) {
  $mp4 = Join-Path $out "MESFlow_User_Guide.mp4"
  & ffmpeg -y -i $webm -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $mp4
  if ($LASTEXITCODE -eq 0) {
    Write-Host "MP4 READY:"
    Write-Host $mp4
  }
} else {
  Write-Host "ffmpeg chưa cài: giữ file WEBM. Cài ffmpeg nếu muốn tự động xuất MP4."
}
