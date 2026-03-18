param(
    [switch]$Debug,
    [switch]$NoServices
)

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "SmartSafe V27 - PowerShell Startup Script" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Function to test command
function Test-Command {
    param([string]$Command, [string]$Name)
    try {
        $result = Invoke-Expression "$Command 2>&1"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ $Name" -ForegroundColor Green
            return $true
        } else {
            Write-Host "✗ $Name failed" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "✗ $Name error: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# Check Python
if (-not (Test-Command "python --version" "Python")) { exit 1 }

# Check Node.js
if (-not (Test-Command "node --version" "Node.js")) { exit 1 }

# Install dependencies if needed
if (-not $NoServices) {
    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    pip install -r requirements_no_compile.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install Python dependencies" -ForegroundColor Red
        exit 1
    }

    Write-Host "Installing Node.js dependencies..." -ForegroundColor Yellow
    Set-Location whatsapp-server
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install Node.js dependencies" -ForegroundColor Red
        exit 1
    }
    Set-Location ..

    # Start services
    Write-Host "Starting WhatsApp server..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd" -ArgumentList "/c cd whatsapp-server && npm start" -NoNewWindow

    Write-Host "Starting metrics server..." -ForegroundColor Yellow
    Start-Job -ScriptBlock {
        python -c "from core.monitoring.metrics import start_metrics_server; start_metrics_server(8001)"
    }

    Write-Host "Waiting for services to start..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}

# Test GUI
Write-Host "Testing GUI..." -ForegroundColor Yellow
python test_gui.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "GUI test failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Starting SmartSafe V27 GUI..." -ForegroundColor Green
Write-Host "Close this window to stop all services" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if ($Debug) {
    python main.py
} else {
    # Start GUI and keep PowerShell window open
    $guiJob = Start-Job -ScriptBlock { python main.py }
    Wait-Job $guiJob
    Receive-Job $guiJob
}

Write-Host ""
Write-Host "SmartSafe GUI closed." -ForegroundColor Yellow
Write-Host "Services may still be running." -ForegroundColor Yellow
Read-Host "Press Enter to exit"