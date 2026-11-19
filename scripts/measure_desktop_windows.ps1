param([Parameter(Mandatory=$true)][string]$Exe)

$ErrorActionPreference = 'Stop'
$binary = (Resolve-Path -LiteralPath $Exe).Path
$profileRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("eai-window-test-" + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $profileRoot
$measurements = foreach ($launch in 1..2) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $binary
    $info.WorkingDirectory = (Split-Path -LiteralPath $binary)
    $info.UseShellExecute = $false
    $info.EnvironmentVariables['LOCALAPPDATA'] = $profileRoot
    $info.EnvironmentVariables['PATH'] = Join-Path $env:SystemRoot 'System32'
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $boot = [Diagnostics.Process]::Start($info)
    $gui = $null
    try {
        while ($watch.Elapsed.TotalSeconds -lt 60 -and -not $boot.HasExited) {
            $child = Get-Process -Name EAI -ErrorAction SilentlyContinue | Where-Object {
                $_.Path -eq $binary -and $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like 'EAI*'
            }
            foreach ($candidate in $child) {
                $parentPid = (Get-CimInstance Win32_Process -Filter ("ProcessId=" + $candidate.Id)).ParentProcessId
                if ($parentPid -eq $boot.Id) { $gui = $candidate; break }
            }
            if ($gui) { break }
            Start-Sleep -Milliseconds 60
        }
        if (-not $gui) { throw 'Native workstation window did not open.' }
        $readyMs = $watch.ElapsedMilliseconds
        Start-Sleep -Milliseconds 700
        $gui.Refresh()
        $boot.Refresh()
        $idleMiB = [Math]::Round(($gui.WorkingSet64 + $boot.WorkingSet64) / 1MB, 1)
        $cpuMs = [int]($gui.TotalProcessorTime.TotalMilliseconds + $boot.TotalProcessorTime.TotalMilliseconds)
        $closing = [Diagnostics.Stopwatch]::StartNew()
        if (-not $gui.CloseMainWindow()) { throw 'Window close request failed.' }
        if (-not $boot.WaitForExit(15000) -or $boot.ExitCode -ne 0) { throw 'Workstation exit failed.' }
        [ordered]@{launch=$launch; window_ms=$readyMs; idle_working_set_mib=$idleMiB;
                   boot_cpu_ms=$cpuMs; close_ms=$closing.ElapsedMilliseconds; exit_code=$boot.ExitCode}
    } finally {
        if ($gui) { $gui.Dispose() }
        $boot.Dispose()
    }
}
[ordered]@{
    os_build=[Environment]::OSVersion.Version.Build
    sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
    bytes=(Get-Item -LiteralPath $binary).Length
    samples=@($measurements)
} | ConvertTo-Json -Depth 4
