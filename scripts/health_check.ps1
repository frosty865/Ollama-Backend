$ErrorActionPreference = 'SilentlyContinue'
$resp = Invoke-RestMethod -Uri 'http://localhost:8000/status'
if ($null -eq $resp -or $resp.status -ne 'ok') {
  try { Restart-Service -Name 'VOFCBackend' -ErrorAction Stop } catch {}
}


