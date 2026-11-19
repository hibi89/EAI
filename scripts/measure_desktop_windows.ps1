# P2-08/UX04: read-only by default. An owner must explicitly opt in to
# executing the named development binary. Not a physical Win11 acceptance.
param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [switch]$RunWithOwnerConsent
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') {
    throw 'Native Windows host required; no execution attempted.'
}

$item = Get-Item -LiteralPath $Exe -ErrorAction Stop
if ($item.PSIsContainer -or $item.Name -cne 'EAI.exe' -or $item.Length -le 512) {
    throw 'Explicit nonempty EAI.exe development candidate required.'
}
$reparse = [System.IO.FileAttributes]::ReparsePoint
$walk = $item
while ($null -ne $walk) {
    if (($walk.Attributes -band $reparse) -ne 0) {
        throw 'Linked executable or ancestor is not trusted.'
    }
    if ($walk -is [System.IO.FileInfo]) { $walk = $walk.Directory }
    else { $walk = $walk.Parent }
}

$binary = $item.FullName
$stream = [System.IO.File]::Open(
    $binary, [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
try {
    $magic = New-Object byte[] 2
    if ($stream.Read($magic, 0, 2) -ne 2 -or
            $magic[0] -ne 77 -or $magic[1] -ne 90) {
        throw 'Not a PE executable; no execution attempted.'
    }
} finally {
    $stream.Dispose()
}
$sha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
$evidence = [ordered]@{
    schema = 'eai.windows.owner_measurement.v2'
    status = 'PREFLIGHT_ONLY'
    mode = 'READ_ONLY'
    executable_sha256 = $sha256
    bytes = $item.Length
    os_build = [Environment]::OSVersion.Version.Build
    launch_consent = $false
    network_checked = 'NOT_RUN'
    korean_ime_checked = 'NOT_RUN'
    dpi_checked = 'NOT_RUN'
    physical_ux_acceptance = 'NOT_RUN'
    samples = @()
}
if (-not $RunWithOwnerConsent) {
    $evidence | ConvertTo-Json -Depth 5
    return
}

# The opt-in allows exactly two local launches in an isolated, disposable
# profile. It does not authorize original writes, external API calls, or
# any P26/real Player side effects.
$profileRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    'eai-window-measure-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $profileRoot -ErrorAction Stop
$measurements = @()
try {
    foreach ($launch in 1..2) {
        if ((Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant() -cne $sha256) {
            throw 'EXE bytes changed before launch; measurement refused.'
        }
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $binary
        $info.WorkingDirectory = $item.DirectoryName
        $info.UseShellExecute = $false
        foreach ($key in @('LOCALAPPDATA', 'APPDATA', 'TEMP', 'TMP', 'USERPROFILE')) {
            $info.EnvironmentVariables[$key] = $profileRoot
        }
        $info.EnvironmentVariables['PATH'] = Join-Path $env:SystemRoot 'System32'

        $boot = $null
        $gui = $null
        $timer = [Diagnostics.Stopwatch]::StartNew()
        try {
            $boot = [Diagnostics.Process]::Start($info)
            if ($null -eq $boot) { throw 'Failed to launch isolated EAI process.' }
            while ($timer.Elapsed.TotalSeconds -lt 60 -and -not $boot.HasExited) {
                $boot.Refresh()
                if ($boot.MainWindowHandle -ne [IntPtr]::Zero) {
                    $gui = $boot
                    break
                }
                # Search only children of this exact process ID. Never send
                # messages to unrelated existing EAI windows.
                $children = @(Get-CimInstance Win32_Process -Filter (
                    'ParentProcessId=' + $boot.Id) -ErrorAction SilentlyContinue)
                foreach ($child in $children) {
                    if ($child.Name -ine 'EAI.exe') { continue }
                    $candidate = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
                    if ($null -eq $candidate) { continue }
                    try {
                        if ($candidate.Path -ceq $binary -and
                                $candidate.MainWindowHandle -ne [IntPtr]::Zero -and
                                $candidate.MainWindowTitle -like 'EAI*') {
                            $gui = $candidate
                            break
                        }
                    } catch {
                        # Child exited during inspection. Never fall back to
                        # searching unrelated windows or processes.
                    }
                    $candidate.Dispose()
                }
                if ($null -ne $gui) { break }
                Start-Sleep -Milliseconds 70
            }
            if ($null -eq $gui) { throw 'Owned native GUI window not found; measurement failed.' }

            $windowMs = $timer.ElapsedMilliseconds
            Start-Sleep -Milliseconds 700
            $gui.Refresh()
            $boot.Refresh()
            $memoryBytes = [long]$gui.WorkingSet64
            $cpuMs = [double]$gui.TotalProcessorTime.TotalMilliseconds
            if ($gui.Id -ne $boot.Id) {
                $memoryBytes += [long]$boot.WorkingSet64
                $cpuMs += $boot.TotalProcessorTime.TotalMilliseconds
            }
            $closing = [Diagnostics.Stopwatch]::StartNew()
            if (-not $gui.CloseMainWindow()) { throw 'Owned GUI close request failed.' }
            if ($gui.Id -ne $boot.Id -and -not $gui.WaitForExit(15000)) {
                throw 'Owned GUI child did not exit.'
            }
            if (-not $boot.WaitForExit(15000) -or $boot.ExitCode -ne 0) {
                throw 'Owned EAI launcher did not exit cleanly.'
            }
            $measurements += [ordered]@{
                launch = $launch
                window_ms = $windowMs
                idle_working_set_mib = [Math]::Round($memoryBytes / 1MB, 1)
                boot_cpu_ms = [int]$cpuMs
                close_ms = $closing.ElapsedMilliseconds
                exit_code = $boot.ExitCode
            }
        } finally {
            # Cleanup is PID-scoped: never Stop-Process -Name EAI.
            if ($null -ne $gui -and $null -ne $boot -and $gui.Id -ne $boot.Id) {
                try {
                    if (-not $gui.HasExited) {
                        $gui.Kill()
                        $null = $gui.WaitForExit(5000)
                    }
                } catch {}
                $gui.Dispose()
            }
            if ($null -ne $boot) {
                try {
                    if (-not $boot.HasExited) {
                        $boot.Kill()
                        $null = $boot.WaitForExit(5000)
                    }
                } catch {}
                $boot.Dispose()
            }
        }
    }
    if ((Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant() -cne $sha256) {
        throw 'EXE bytes changed during measurement.'
    }
    $evidence.status = 'MEASURED_REQUIRES_OWNER_REVIEW'
    $evidence.mode = 'OWNER_CONSENTED_ISOLATED'
    $evidence.launch_consent = $true
    $evidence.samples = @($measurements)
} finally {
    # Remove only the uniquely created profile. Retain an unexpected linked
    # tree rather than recurse through a possible owner-controlled junction.
    if (Test-Path -LiteralPath $profileRoot) {
        $folder = Get-Item -LiteralPath $profileRoot -Force
        $links = @(Get-ChildItem -LiteralPath $profileRoot -Force -Recurse |
            Where-Object { ($_.Attributes -band $reparse) -ne 0 })
        if (($folder.Attributes -band $reparse) -ne 0 -or $links.Count -ne 0) {
            throw 'Unexpected link in measurement profile; manual review required.'
        }
        Remove-Item -LiteralPath $profileRoot -Force -Recurse -ErrorAction Stop
    }
}
$evidence | ConvertTo-Json -Depth 5
