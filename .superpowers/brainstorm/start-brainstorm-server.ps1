param([string]$SessionDir,[string]$ServerScript)
$env:BRAINSTORM_DIR = $SessionDir
$env:BRAINSTORM_HOST = "127.0.0.1"
$env:BRAINSTORM_URL_HOST = "localhost"
Remove-Item Env:\BRAINSTORM_OWNER_PID -ErrorAction SilentlyContinue
Set-Location (Split-Path -Parent $ServerScript)
node $ServerScript
