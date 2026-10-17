# Download files from the gemma-4-developer-agent competition into .\data
# Usage:
#   .\download-data.ps1 tasks.jsonl sample_submission docker sandbox wheels
#   .\download-data.ps1 embeddings graphs                 (~850 MB)
#   .\download-data.ps1 snapshots                         (~20 GB)
#   .\download-data.ps1 -TaskIds httpx_3672,rich_3061     (snapshot + graph + embeddings per task)
# Positional arguments are top-level file or folder names.
param(
    [Parameter(ValueFromRemainingArguments)][string[]]$Prefixes = @(),
    [string[]]$TaskIds = @()
)

$comp = 'gemma-4-developer-agent'
$kaggle = "$PSScriptRoot\.venv\Scripts\kaggle.exe"
$dataDir = "$PSScriptRoot\data"
. "$PSScriptRoot\load-env.ps1"

# List every file (the API pages results)
$files = @()
$token = $null
do {
    $cmdArgs = @('competitions', 'files', $comp, '-v', '--page-size', '200')
    if ($token) { $cmdArgs += @('--page-token', $token) }
    $token = $null
    foreach ($line in (& $kaggle @cmdArgs 2>&1 | Out-String) -split "`r?`n") {
        if ($line -match '^Next Page Token = (.+)$') { $token = $Matches[1].Trim() }
        elseif ($line -match '^([^,]+),\d+,') { $files += $Matches[1] }
    }
} while ($token)

# Per-task files: snapshots/<instance_id>.tgz, graphs|embeddings/<repo>_<base_commit>.*
$taskKeys = @()
if ($TaskIds) {
    $tasksFile = Join-Path $dataDir 'tasks.jsonl'
    if (-not (Test-Path $tasksFile)) { throw "Download tasks.jsonl first: .\download-data.ps1 tasks.jsonl" }
    $tasks = Get-Content $tasksFile | ForEach-Object { $_ | ConvertFrom-Json }
    foreach ($id in $TaskIds) {
        $t = $tasks | Where-Object instance_id -eq $id
        if (-not $t) { throw "Unknown task id: $id" }
        $taskKeys += "snapshots/$id."
        $repo = ($t.repo -split '/')[-1].ToLower()
        $taskKeys += "graphs/${repo}_$($t.base_commit)."
        $taskKeys += "embeddings/${repo}_$($t.base_commit)."
    }
}

$wanted = $files | Where-Object {
    $f = $_
    ($Prefixes -contains ($f -split '/')[0]) -or ($taskKeys | Where-Object { $f.StartsWith($_) })
}
Write-Host "Downloading $(@($wanted).Count) files..."
foreach ($f in $wanted) {
    $dest = Join-Path $dataDir (Split-Path $f -Parent)
    if (Test-Path (Join-Path $dataDir $f)) { continue }   # skip already downloaded
    & $kaggle competitions download $comp -f $f -p $dest -q
    # Large files arrive zipped; unpack and remove the zip
    $zip = Join-Path $dest ((Split-Path $f -Leaf) + '.zip')
    if (Test-Path $zip) { Expand-Archive $zip -DestinationPath $dest -Force; Remove-Item $zip }
}
Write-Host "Done."
