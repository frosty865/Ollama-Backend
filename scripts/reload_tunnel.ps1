Write-Host "Restarting Cloudflared and VOFCBackend services..."
Restart-Service cloudflared -ErrorAction SilentlyContinue
Restart-Service VOFCBackend -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "Services restarted successfully at $timestamp"
"[$timestamp] Restarted Cloudflared and VOFCBackend" | Out-File "C:\Users\frost\AppData\Local\Ollama\logs\restart.log" -Append


