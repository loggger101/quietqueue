<#
.SYNOPSIS
  Freeze or unfreeze the running campaign without losing the in-flight cell.

.DESCRIPTION
  A campaign cell is 0.5-8 h of compute that writes NOTHING until it finishes,
  so killing the queue mid-cell throws that cell away entirely.  Suspending the
  process tree frees every core immediately and keeps the work: Windows also
  trims a suspended process's working set, so the tree held 0.4 GB rather than
  the ~25 GB it had resident (measured 2026-09-12, pausing leo benef+search
  5.7 h in).

  Processes are found by command line, never by a remembered pid, because pids
  do not survive the pause they are meant to outlive.

  [!]  A reboot while suspended loses the in-flight cell, exactly as killing it
  would -- the queue resumes at that cell from the beginning.  Everything
  already in campaign/results.csv with rc == 0 is safe on disk either way.

  Every parameter but -Resume defaults to this campaign's value, so the two
  examples below are all the campaign needs.

.PARAMETER Resume
  Thaw instead of freeze.

.PARAMETER Match
  Command-line patterns (PowerShell -like) naming the roots of the trees to
  freeze; every descendant of a root is frozen with it.

.PARAMETER ProcessName
  The WQL LIKE pattern for the process names searched, roots and descendants
  alike.

.PARAMETER TaskName
  The scheduled task whose reboot trigger tracks the pause.  Empty, or a task
  this machine does not have, leaves the scheduler alone and says so.

.EXAMPLE
  powershell -File campaign\_pause.ps1            # freeze
  powershell -File campaign\_pause.ps1 -Resume    # thaw and carry on
#>
param(
  [switch]$Resume,
  [string[]]$Match = @('*run_queue*', '*memwatch*'),
  [string]$ProcessName = 'python%',
  [string]$TaskName = 'economicspace_campaign'
)

Add-Type -Name Nt -Namespace W -MemberDefinition @'
[DllImport("ntdll.dll")] public static extern uint NtSuspendProcess(IntPtr h);
[DllImport("ntdll.dll")] public static extern uint NtResumeProcess(IntPtr h);
[DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(uint a, bool i, int p);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
'@

$all = Get-CimInstance Win32_Process -Filter "Name like '$ProcessName'"
$byParent = @{}
foreach ($p in $all) {
  if (-not $byParent[$p.ParentProcessId]) { $byParent[$p.ParentProcessId] = @() }
  $byParent[$p.ParentProcessId] += $p
}
$roots = @(foreach ($p in $all) {
  foreach ($m in $Match) { if ($p.CommandLine -like $m) { $p; break } }
})
if (-not $roots) { Write-Host "no campaign processes found - nothing to do"; exit 0 }

$targets = New-Object System.Collections.ArrayList
function Collect($proc) {
  [void]$targets.Add($proc)
  foreach ($c in $byParent[$proc.ProcessId]) { Collect $c }
}
foreach ($r in $roots) { Collect $r }

$verb = if ($Resume) { "resuming" } else { "suspending" }
Write-Host "$verb $($targets.Count) processes"
foreach ($t in $targets) {
  $h = [W.Nt]::OpenProcess(0x0800, $false, $t.ProcessId)   # PROCESS_SUSPEND_RESUME
  if ($h -eq [IntPtr]::Zero) { Write-Host "  could not open pid $($t.ProcessId)"; continue }
  if ($Resume) { [void][W.Nt]::NtResumeProcess($h) } else { [void][W.Nt]::NtSuspendProcess($h) }
  [void][W.Nt]::CloseHandle($h)
}

# The AtLogOn trigger is what restarts the campaign after a reboot, so it
# tracks the pause: leaving it armed while paused would resume the campaign
# behind your back at the next logon.  A machine without the task (the other
# host, or one that never registered it) used to get an error here after the
# processes had already been frozen; it now gets a line saying so.
$task = if ($TaskName) { Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
if (-not $task) {
  $named = if ($TaskName) { "no scheduled task '$TaskName' here" } else { "no scheduled task named" }
  Write-Host "$named - reboot trigger left alone"
}
elseif ($Resume) { Enable-ScheduledTask  -TaskName $TaskName | Out-Null; Write-Host "reboot trigger re-armed" }
else             { Disable-ScheduledTask -TaskName $TaskName | Out-Null; Write-Host "reboot trigger disarmed" }
