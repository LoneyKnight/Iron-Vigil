# Kill leftover Godot processes.
#
# Godot's console wrapper exits while the GUI child keeps running, so a test run that is
# interrupted (or whose script fails to compile and never reaches its own watchdog) leaves
# processes behind. They hold the window, and enough of them make the next run unreliable.
#
# Usage:  pwsh -File tools/run/kill-godot.ps1
$procs = Get-Process -Name 'Godot*' -ErrorAction SilentlyContinue
if (-not $procs) {
    Write-Host "no Godot processes"
    exit 0
}
$n = ($procs | Measure-Object).Count
$procs | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
$left = (Get-Process -Name 'Godot*' -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "killed $n Godot process(es), $left remaining"
