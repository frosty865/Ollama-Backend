# ===============================================
# start_all.ps1
# VOFC / Ollama Master Autorun Startup Script
# ===============================================

$base      = "C:\Users\frost\AppData\Local\Ollama\automation"
$python    = (Get-Command python).Source
$logDir    = "$base\logs"
$ollamaUrl = "https://ollama.frostech.site"  # Remote Ollama server
$model     = "vofc-engine"

# -------------------------------
# Utility Functions
# -------------------------------

function Write-Log {
    param([string]$msg)
    $timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    Write-Host "[$timestamp] $msg"
}

# -------------------------------
# 1️⃣ Ensure log directory
# -------------------------------
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# -------------------------------
# 2️⃣ Check remote Ollama API availability
# -------------------------------
Write-Log "🌐 Checking remote Ollama server: $ollamaUrl"
$ollamaReady = $false
for ($i = 0; $i -lt 10; $i++) {
    try {
        $ping = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -TimeoutSec 5 -SkipCertificateCheck
        if ($ping) { $ollamaReady = $true; break }
    } catch {
        Write-Log "⏳ Waiting for Ollama API... (attempt $($i+1)/10)"
        Start-Sleep -Seconds 2
    }
}
if (-not $ollamaReady) {
    Write-Log "❌ Ollama API not responding at $ollamaUrl"
    Write-Log "⚠️ Please ensure the remote Ollama server is running."
    exit 1
}
Write-Log "✅ Ollama API reachable at $ollamaUrl"

# -------------------------------
# 4️⃣ Preload model into memory
# -------------------------------
Write-Log "🧠 Preloading model: $model ..."
try {
    Invoke-RestMethod -Uri "$ollamaUrl/api/generate" `
        -Method POST `
        -Body (@{model=$model; prompt="ping"} | ConvertTo-Json) `
        -ContentType "application/json" `
        -TimeoutSec 30 `
        -SkipCertificateCheck | Out-Null
    Write-Log "✅ Model preloaded successfully."
} catch {
    Write-Log "⚠️ Model preload failed: $($_.Exception.Message)"
}

# -------------------------------
# 5️⃣ Define autorun scripts (check both locations)
# -------------------------------
$scripts = @(
    "ollama_auto_processor.py",
    "vofc_pipeline.py"
)

# Optional scripts in scripts/ folder
$optionalScripts = @(
    "vofc_collector.py",
    "heuristic_pipeline.py",
    "safe_ingestor.py"
)

# -------------------------------
# 6️⃣ Launch each script
# -------------------------------
foreach ($script in $scripts) {
    # First check in automation root
    $scriptPath = "$base\$script"
    
    # If not found, check scripts folder
    if (-not (Test-Path $scriptPath)) {
        $scriptPath = "$base\scripts\$script"
    }
    
    $logFile = "$logDir\$($script -replace '\.py$', '').log"

    # Check if already running
    $running = Get-WmiObject Win32_Process | Where-Object {
        $_.CommandLine -like "*$script*"
    }
    
    if ($running) {
        Write-Log "⚠️ $script is already running. Skipping."
        continue
    }

    if (Test-Path $scriptPath) {
        Write-Log "▶ Starting $script ..."
        Start-Process -FilePath $python `
                      -ArgumentList "`"$scriptPath`"" `
                      -WorkingDirectory $base `
                      -RedirectStandardOutput $logFile `
                      -RedirectStandardError $logFile `
                      -WindowStyle Hidden
        Start-Sleep -Milliseconds 500  # Small delay between launches
    } else {
        Write-Log "⚠️ Missing script: $script"
    }
}

# Launch optional scripts if they exist
foreach ($script in $optionalScripts) {
    $scriptPath = "$base\scripts\$script"
    $logFile    = "$logDir\$($script -replace '\.py$', '').log"

    if (Test-Path $scriptPath) {
        $running = Get-WmiObject Win32_Process | Where-Object {
            $_.CommandLine -like "*$script*"
        }
        
        if (-not $running) {
            Write-Log "▶ Starting optional script: $script ..."
            Start-Process -FilePath $python `
                          -ArgumentList "`"$scriptPath`"" `
                          -WorkingDirectory $base `
                          -RedirectStandardOutput $logFile `
                          -RedirectStandardError $logFile `
                          -WindowStyle Hidden
            Start-Sleep -Milliseconds 500
        }
    }
}

Write-Log "✅ All autorun scripts started."
Write-Log "Logs directory: $logDir"

