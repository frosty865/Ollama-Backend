# VOFC Autorun Service

Automated startup system for VOFC/Ollama processing pipeline.

## Quick Start

### Install the Service

1. **Open PowerShell as Administrator**

2. **Navigate to the autorun folder:**
   ```powershell
   cd "C:\Users\frost\AppData\Local\Ollama\automation\autorun"
   ```

3. **Set execution policy (one-time):**
   ```powershell
   Set-ExecutionPolicy RemoteSigned -Scope Process
   ```

4. **Install the service:**
   ```powershell
   .\Install-VOFCAutorunService.ps1
   ```

### What Gets Started Automatically

On Windows boot, the service will:
- ✅ Start Ollama daemon (if not running)
- ✅ Wait for Ollama API to be ready
- ✅ Preload `vofc-engine` model into memory
- ✅ Start `ollama_auto_processor.py` (file watcher)
- ✅ Start `vofc_pipeline.py` (if needed)

### Manual Operations

**Test the startup script:**
```powershell
.\start_all.ps1
```

**Check service status:**
```powershell
Get-ScheduledTask -TaskName VOFCAutorun
```

**Start service manually:**
```powershell
Start-ScheduledTask -TaskName VOFCAutorun
```

**Stop service:**
```powershell
Stop-ScheduledTask -TaskName VOFCAutorun
```

**View logs:**
```powershell
Get-Content "C:\Users\frost\AppData\Local\Ollama\automation\logs\*.log" -Tail 50
```

**Uninstall service:**
```powershell
.\Install-VOFCAutorunService.ps1 -Uninstall
```

## Troubleshooting

### Service won't start
- Check logs in `automation\logs\`
- Verify Ollama is installed at: `C:\Program Files\Ollama\ollama.exe`
- Ensure Python is in PATH: `python --version`

### Scripts not starting
- Check Task Scheduler → `VOFCAutorun` → Last Run Result
- Verify scripts exist in `automation\` folder
- Check `.env` file is configured correctly

### Ollama connection issues
- Test remote Ollama API: `curl https://ollama.frostech.site/api/tags`
- Check port 11434 is not blocked by firewall

## Configuration

Edit `start_all.ps1` to:
- Change Ollama executable path
- Modify model name
- Add/remove startup scripts
- Adjust retry timeouts

## Auto-Restart on Failure

The service is configured to automatically restart up to 3 times if it fails, with 1-minute intervals between restarts.

To modify restart behavior:
1. Open **Task Scheduler**
2. Navigate to **Task Scheduler Library** → **VOFCAutorun**
3. Right-click → **Properties** → **Settings** tab
4. Configure restart options

