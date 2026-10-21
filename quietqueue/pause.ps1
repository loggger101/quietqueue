<#
.SYNOPSIS
  Freeze or unfreeze a running queue without losing the in-flight job.

.DESCRIPTION
  A job that writes NOTHING until it finishes is lost entirely if the queue is
  killed mid-job.  Suspending the process tree frees every core immediately and
  keeps the work: Windows also trims a suspended process's working set, so in
  economicspace's campaign a 16-process tree 5.7 h into a cell held 0.4 GB
  rather than the ~25 GB it had resident.

  Processes are found by command line, never by a remembered pid, because pids
  do not survive the pause they are meant to outlive.

  [!]  A reboot while suspended loses the in-flight job, exactly as killing it
  would.  A queue that resumes from a ledger restarts that job from the
  beginning.

  [!]  A suspend-based pause inflates any wall clock measured across it.

.PARAMETER Resume
  Thaw instead of freeze.

.PARAMETER Match
  Command-line patterns (PowerShell -like) naming the roots of the trees to
  freeze; every descendant of a root is frozen with it.  Required.

.PARAMETER ProcessName
  The WQL LIKE pattern for the process names searched, roots and descendants
  alike.

.PARAMETER TaskName
  A scheduled task whose trigger tracks the pause: disabled on freeze, enabled
  on resume, so a logon trigger cannot restart a paused queue behind your
  back.  Empty, or a task this machine does not have, leaves the scheduler
  alone and says so.

.EXAMPLE
  powershell -File pause.ps1 -Match '*my_queue*','*memwatch*' -TaskName my_queue
  powershell -File pause.ps1 -Match '*my_queue*','*memwatch*' -TaskName my_queue -Resume
#>
param(
  [switch]$Resume,
  [string[]]$Match = @(),
  [string]$ProcessName = 'python%',
  [string]$TaskName = ''
)

# Not [Parameter(Mandatory)]: a mandatory parameter PROMPTS when missing, and a
# prompt hangs a script run from a scheduler or another program.
if (-not $Match) { Write-Host "pause.ps1: -Match is required (see Get-Help pause.ps1 -Full)"; exit 2 }

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
if (-not $roots) { Write-Host "no matching processes found - nothing to do"; exit 0 }

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

$task = if ($TaskName) { Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
if (-not $task) {
  $named = if ($TaskName) { "no scheduled task '$TaskName' here" } else { "no scheduled task named" }
  Write-Host "$named - its trigger left alone"
}
elseif ($Resume) { Enable-ScheduledTask  -TaskName $TaskName | Out-Null; Write-Host "trigger re-armed" }
else             { Disable-ScheduledTask -TaskName $TaskName | Out-Null; Write-Host "trigger disarmed" }
