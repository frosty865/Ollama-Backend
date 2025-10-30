# ===============================================
# Install-VOFCAutorunService.ps1
# Installs VOFC Autorun as a Windows Service
# ===============================================

param(
    [switch]$Uninstall
)

$serviceName = "VOFCAutorun"
$serviceDisplayName = "VOFC Automation Autorun"
$serviceDescription = "Automatically starts Ollama and VOFC processing scripts on system boot"
$scriptPath = "C:\Users\frost\AppData\Local\Ollama\automation\autorun\start_all.ps1"

# Check for administrator privileges
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "❌ This script requires Administrator privileges." -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    exit 1
}

function Write-Log {
    param([string]$msg, [string]$color = "White")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $msg" -ForegroundColor $color
}

if ($Uninstall) {
    Write-Log "Uninstalling $serviceName service..." "Yellow"
    
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    
    if ($service) {
        if ($service.Status -eq "Running") {
            Write-Log "Stopping service..." "Yellow"
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        
        Write-Log "Removing service..." "Yellow"
        sc.exe delete $serviceName | Out-Null
        Start-Sleep -Seconds 2
        
        $check = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if (-not $check) {
            Write-Log "✅ Service uninstalled successfully!" "Green"
        } else {
            Write-Log "❌ Failed to uninstall service" "Red"
        }
    } else {
        Write-Log "⚠️ Service not found. Nothing to uninstall." "Yellow"
    }
    
    exit 0
}

# Check if script exists
if (-not (Test-Path $scriptPath)) {
    Write-Log "❌ Script not found at: $scriptPath" "Red"
    exit 1
}

# Check if service already exists
$existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue

if ($existingService) {
    Write-Log "⚠️ Service '$serviceName' already exists!" "Yellow"
    $response = Read-Host "Do you want to reinstall it? (Y/N)"
    if ($response -ne "Y" -and $response -ne "y") {
        Write-Log "Installation cancelled." "Yellow"
        exit 0
    }
    
    # Stop and remove existing service
    if ($existingService.Status -eq "Running") {
        Write-Log "Stopping existing service..." "Yellow"
        Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    
    Write-Log "Removing existing service..." "Yellow"
    sc.exe delete $serviceName | Out-Null
    Start-Sleep -Seconds 3
}

Write-Log "Installing $serviceName service..." "Cyan"

# Create PowerShell script wrapper that will be executed by the service
$wrapperScript = @"
`$ErrorActionPreference = 'Continue'
`$scriptPath = '$scriptPath'
Set-Location (Split-Path `$scriptPath -Parent)
& `$scriptPath
"@

$wrapperPath = "$env:TEMP\VOFCAutorunWrapper.ps1"
$wrapperScript | Out-File -FilePath $wrapperPath -Encoding UTF8 -Force

# Use PowerShell to execute the service
# Note: NSSM (Non-Sucking Service Manager) or Task Scheduler are better alternatives
# For now, we'll use Task Scheduler approach which is more reliable

# Create scheduled task instead (runs as SYSTEM on boot, more reliable than service)
$taskName = $serviceName
$taskDescription = $serviceDescription
$taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$taskTrigger = New-ScheduledTaskTrigger -AtStartup
$taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

try {
    # Remove existing task if it exists
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    
    # Register the new task
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $taskAction `
        -Trigger $taskTrigger `
        -Principal $taskPrincipal `
        -Settings $taskSettings `
        -Description $taskDescription `
        -Force | Out-Null
    
    Write-Log "✅ Service installed successfully as Scheduled Task!" "Green"
    Write-Log "Task Name: $taskName" "Cyan"
    Write-Log "The automation will start automatically on system boot." "Green"
    
    # Optionally start it now
    $startNow = Read-Host "Do you want to start it now? (Y/N)"
    if ($startNow -eq "Y" -or $startNow -eq "y") {
        Start-ScheduledTask -TaskName $taskName
        Write-Log "✅ Task started!" "Green"
    }
    
    Write-Log "" "White"
    Write-Log "To manage the service:" "Cyan"
    Write-Log "  Start:   Start-ScheduledTask -TaskName $taskName" "White"
    Write-Log "  Stop:    Stop-ScheduledTask -TaskName $taskName" "White"
    Write-Log "  Status:  Get-ScheduledTask -TaskName $taskName" "White"
    Write-Log "  Remove:  Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false" "White"
    Write-Log "" "White"
    Write-Log "To configure auto-restart on failure:" "Cyan"
    Write-Log "  See: Task Scheduler → $taskName → Properties → Actions tab" "White"
    
} catch {
    Write-Log "❌ Failed to install service: $($_.Exception.Message)" "Red"
    exit 1
}

