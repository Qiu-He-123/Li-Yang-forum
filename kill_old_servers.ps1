$root = $PSScriptRoot

$procs = Get-CimInstance Win32_Process | Where-Object {
    (($_.CommandLine -like '*uvicorn app.main*') -or ($_.CommandLine -like '*vite*')) -and
    ($_.CommandLine -like ('*' + $root + '*'))
}

foreach ($p in $procs) {
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    } catch {
        # already gone
    }
}

Write-Host ("Stopped " + @($procs).Count + " old process(es).")
