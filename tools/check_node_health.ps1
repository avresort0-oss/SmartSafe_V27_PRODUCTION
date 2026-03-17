param(
    [string]$Url = "http://127.0.0.1:4000/health",
    [int]$TimeoutSec = 2
)

$ErrorActionPreference = "Stop"

try {
    $resp = Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec
    if ($null -ne $resp -and $resp.ok -eq $true) {
        exit 0
    }
    exit 1
}
catch {
    exit 1
}
