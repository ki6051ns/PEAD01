param(
    [ValidateSet('all','paths','search','ensemble','walkforward','report')]
    [string]$Mode = 'all',
    [ValidateRange(1,256)][int]$Workers = 4,
    [ValidateRange(256,1048576)][int]$MemoryMiB = 4096
)
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv/Scripts/python.exe'
$log = Join-Path $root 'data/phase6_v6/logs'
New-Item -ItemType Directory -Force $log | Out-Null
$env:PYTHONPATH = Join-Path $root 'src'
$env:OPENBLAS_NUM_THREADS = '1'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$arguments = @('-m','pead01.phase6','--mode',$Mode,'--workers',$Workers,'--memory-mib',$MemoryMiB,'--resume')
$job = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $log "$stamp.out.log") -RedirectStandardError (Join-Path $log "$stamp.err.log") -PassThru
Write-Output "Phase 6 PID $($job.Id)"
