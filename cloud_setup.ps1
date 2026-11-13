# cloud_setup.ps1 -- One-command setup for the LocalStack cloud demo.
#
# Usage:
#   .\cloud_setup.ps1
#
# Prerequisites: Docker Desktop running, Python venv activated.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Saga Cloud Demo Setup ===" -ForegroundColor Cyan
Write-Host ""

# 1. Start LocalStack
Write-Host "[1/4] Starting LocalStack container..." -ForegroundColor Yellow
docker-compose -f cloud/setup/docker-compose.yml up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: docker-compose failed. Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

# 2. Wait for LocalStack to be ready
Write-Host "[2/4] Waiting for LocalStack to be ready..." -ForegroundColor Yellow
$maxRetries = 30
$retryCount = 0
$ready = $false

while (-not $ready -and $retryCount -lt $maxRetries) {
    Start-Sleep -Seconds 2
    $retryCount++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:4566/_localstack/health" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $ready = $true
        }
    } catch {
        Write-Host "  Waiting... ($retryCount/$maxRetries)" -ForegroundColor Gray
    }
}

if (-not $ready) {
    Write-Host "ERROR: LocalStack did not become ready in time." -ForegroundColor Red
    exit 1
}
Write-Host "  LocalStack is ready." -ForegroundColor Green

# 3. Install boto3 if needed
Write-Host "[3/4] Ensuring boto3 is installed..." -ForegroundColor Yellow
.venv\Scripts\python.exe -m pip install boto3 --quiet

# 4. Create DynamoDB tables and SNS topics
Write-Host "[4/4] Creating DynamoDB tables and SNS topics..." -ForegroundColor Yellow
.venv\Scripts\python.exe -m cloud.setup.create_resources

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Run the smoke test:  .venv\Scripts\python.exe cloud_smoke_test.py"
Write-Host "Run the cloud demo:  .venv\Scripts\python.exe cloud_demo.py"
Write-Host ""
