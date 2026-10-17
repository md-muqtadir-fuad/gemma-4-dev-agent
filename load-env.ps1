# Load variables from .env into the current PowerShell session.
# Usage (note the leading dot):  . .\load-env.ps1
Get-Content "$PSScriptRoot\.env" | ForEach-Object {
    if ($_ -match '^\s*([^#=\s][^=]*?)\s*=\s*(.+?)\s*$') {
        Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2]
    }
}
