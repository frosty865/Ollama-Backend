Write-Host "Starting nightly learning-sync..."
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$logFile = "C:\Users\frost\AppData\Local\Ollama\logs\learning_sync.log"

try {
    & "C:\Users\frost\AppData\Local\Programs\Python\Python311\python.exe" `
        "C:\Users\frost\AppData\Local\Ollama\app\workers\sync_learning.py"
    Write-Host "Learning sync completed at $timestamp"
    "[$timestamp] Sync completed" | Out-File $logFile -Append
}
catch {
    Write-Host "Learning sync failed: $_"
    "[$timestamp] Sync failed: $_" | Out-File $logFile -Append
}


