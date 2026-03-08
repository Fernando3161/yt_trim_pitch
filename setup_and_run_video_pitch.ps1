$ErrorActionPreference = 'Stop'

$SourceEnvName = 'OLD_ENV'
$TargetEnvName = 'VIDEO_PITCH_ENV'
$PythonVersion = '3.11'
$VideoUrl = 'PASTE_YOUR_VIDEO_URL_HERE'
$StartTime = '00:00:00'
$EndTime = '00:02:00'
$OutputFileName = 'clip_medio_tono_abajo.mp4'
$ClipBaseName = 'clip'
$RequirementsFileName = 'requirements.txt'

function Write-Step {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Admin {
    if (Test-IsAdmin) {
        return
    }

    Write-Host 'Requesting Administrator privileges...' -ForegroundColor Yellow
    $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath))
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'powershell.exe'
    $psi.Arguments = ($args -join ' ')
    $psi.Verb = 'runas'
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    exit 0
}

function Get-ScriptDir {
    if ($PSCommandPath) {
        return Split-Path -Parent $PSCommandPath
    }
    return (Get-Location).Path
}

function Get-CondaExe {
    $candidates = @()

    if ($env:CONDA_EXE) {
        $candidates += $env:CONDA_EXE
    }

    foreach ($name in @('conda.exe', 'conda.bat', 'conda')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $candidates += $cmd.Source
        }
    }

    $candidates += @(
        (Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'miniforge3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'mambaforge\Scripts\conda.exe'),
        'C:\ProgramData\Miniconda3\Scripts\conda.exe',
        'C:\ProgramData\Anaconda3\Scripts\conda.exe',
        'C:\ProgramData\miniforge3\Scripts\conda.exe'
    )

    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Invoke-Conda {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$CaptureOutput
    )

    if ($CaptureOutput) {
        $output = & $script:CondaExe @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "Conda command failed: $($Arguments -join ' ')`n$output"
        }
        return $output
    }

    & $script:CondaExe @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Conda command failed: $($Arguments -join ' ')"
    }
}

function Get-CondaEnvNames {
    $jsonText = Invoke-Conda -Arguments @('env', 'list', '--json') -CaptureOutput
    $json = $jsonText | ConvertFrom-Json
    $names = @()

    foreach ($envPath in $json.envs) {
        if (-not [string]::IsNullOrWhiteSpace($envPath)) {
            $names += [System.IO.Path]::GetFileName($envPath)
        }
    }

    return $names | Select-Object -Unique
}

function Ensure-CondaEnvironment {
    param(
        [string]$SourceEnv,
        [string]$TargetEnv,
        [string]$PyVersion
    )

    $envNames = Get-CondaEnvNames

    if ($envNames -contains $TargetEnv) {
        Write-Host "Conda environment '$TargetEnv' already exists." -ForegroundColor Green
        return
    }

    if (-not [string]::IsNullOrWhiteSpace($SourceEnv) -and $SourceEnv -ne 'OLD_ENV' -and ($envNames -contains $SourceEnv)) {
        Write-Host "Creating '$TargetEnv' by cloning '$SourceEnv'..." -ForegroundColor Yellow
        Invoke-Conda -Arguments @('create', '--name', $TargetEnv, '--clone', $SourceEnv, '-y')
        return
    }

    Write-Host "Creating fresh conda environment '$TargetEnv' with Python $PyVersion..." -ForegroundColor Yellow
    Invoke-Conda -Arguments @('create', '--name', $TargetEnv, "python=$PyVersion", '-y')
}

function Ensure-PipAndRequirements {
    param(
        [string]$TargetEnv,
        [string]$RequirementsFile
    )

    Write-Host "Ensuring pip is installed in '$TargetEnv'..." -ForegroundColor Yellow
    Invoke-Conda -Arguments @('install', '-n', $TargetEnv, 'pip', '-y')

    if (Test-Path $RequirementsFile) {
        Write-Host "Installing/updating packages from '$RequirementsFile'..." -ForegroundColor Yellow
        Invoke-Conda -Arguments @('run', '-n', $TargetEnv, 'python', '-m', 'pip', 'install', '-r', $RequirementsFile)
    }
    else {
        Write-Host "No requirements.txt found. Installing yt-dlp directly..." -ForegroundColor Yellow
        Invoke-Conda -Arguments @('run', '-n', $TargetEnv, 'python', '-m', 'pip', 'install', 'yt-dlp')
    }
}

function Get-FFmpegBinDir {
    $cmd = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $dir = Split-Path -Parent $cmd.Source
        if (Test-Path (Join-Path $dir 'ffprobe.exe')) {
            return $dir
        }
    }

    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'),
        (Join-Path $env:ProgramFiles 'WinGet\Packages'),
        (Join-Path ${env:ProgramFiles(x86)} 'WinGet\Packages'),
        'C:\ffmpeg',
        (Join-Path $env:ProgramFiles 'FFmpeg'),
        (Join-Path $env:USERPROFILE 'ffmpeg')
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($root in $roots) {
        $match = Get-ChildItem -Path $root -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) {
            $dir = Split-Path -Parent $match.FullName
            if (Test-Path (Join-Path $dir 'ffprobe.exe')) {
                return $dir
            }
        }
    }

    return $null
}

function Add-ToMachinePathIfMissing {
    param([string]$Directory)

    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $parts = @()
    if ($machinePath) {
        $parts = $machinePath -split ';'
    }

    if ($parts -contains $Directory) {
        if (-not (($env:Path -split ';') -contains $Directory)) {
            $env:Path = "$Directory;$env:Path"
        }
        return
    }

    $newPath = if ([string]::IsNullOrWhiteSpace($machinePath)) { $Directory } else { "$machinePath;$Directory" }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'Machine')
    $env:Path = "$Directory;$env:Path"
}

function Ensure-FFmpegInstalledAndOnPath {
    Write-Step 'Checking FFmpeg and ffprobe'

    $ffmpegBin = Get-FFmpegBinDir
    if (-not $ffmpegBin) {
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) {
            Fail 'winget was not found. Install App Installer / WinGet first.'
        }

        Write-Host 'FFmpeg not found. Installing Gyan.FFmpeg with winget in machine scope...' -ForegroundColor Yellow
        & $winget.Source install -e --id Gyan.FFmpeg --scope machine --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw 'winget failed to install Gyan.FFmpeg.'
        }

        $ffmpegBin = Get-FFmpegBinDir
        if (-not $ffmpegBin) {
            Fail 'FFmpeg seems installed, but ffmpeg.exe could not be located afterwards.'
        }
    }
    else {
        Write-Host "FFmpeg found in: $ffmpegBin" -ForegroundColor Green
    }

    Add-ToMachinePathIfMissing -Directory $ffmpegBin

    $ffmpegCmd = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    $ffprobeCmd = Get-Command ffprobe.exe -ErrorAction SilentlyContinue
    if (-not $ffmpegCmd -or -not $ffprobeCmd) {
        Fail 'PATH was updated, but ffmpeg/ffprobe are still not resolvable in this session.'
    }

    Write-Host "ffmpeg available at: $($ffmpegCmd.Source)" -ForegroundColor Green
    Write-Host "ffprobe available at: $($ffprobeCmd.Source)" -ForegroundColor Green
}

function Get-ClipFile {
    param([string]$Directory, [string]$BaseName)

    $matches = Get-ChildItem -Path $Directory -File -ErrorAction SilentlyContinue |
        Where-Object { $_.BaseName -eq $BaseName } |
        Sort-Object LastWriteTime -Descending

    return $matches | Select-Object -First 1
}

function Test-FFmpegHasRubberband {
    $output = & ffmpeg -hide_banner -filters 2>&1
    return ($output | Select-String -Pattern 'rubberband' -Quiet)
}

function Get-AudioSampleRate {
    param([string]$InputFile)

    $sampleRate = & ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of default=nokey=1:noprint_wrappers=1 $InputFile 2>$null
    if (-not $sampleRate) {
        throw 'Could not determine the input audio sample rate with ffprobe.'
    }

    return [int]($sampleRate | Select-Object -First 1)
}

function Invoke-VideoProcessing {
    param(
        [string]$TargetEnv,
        [string]$WorkDir,
        [string]$Video,
        [string]$Start,
        [string]$End,
        [string]$ClipBase,
        [string]$OutputName
    )

    if ([string]::IsNullOrWhiteSpace($Video) -or $Video -eq 'PASTE_YOUR_VIDEO_URL_HERE') {
        Fail 'Please edit the script and replace PASTE_YOUR_VIDEO_URL_HERE with your actual YouTube URL.'
    }

    Push-Location $WorkDir
    try {
        Write-Step 'Downloading the selected video section'
        Get-ChildItem -Path $WorkDir -File -ErrorAction SilentlyContinue |
            Where-Object { $_.BaseName -eq $ClipBase -or $_.Name -eq $OutputName } |
            Remove-Item -Force -ErrorAction SilentlyContinue

        Invoke-Conda -Arguments @(
            'run', '-n', $TargetEnv,
            'python', '-m', 'yt_dlp',
            '-f', 'bv*+ba/b',
            '--merge-output-format', 'mp4',
            '--force-keyframes-at-cuts',
            '--download-sections', "*$Start-$End",
            '-o', (Join-Path $WorkDir "$ClipBase.%(ext)s"),
            $Video
        )

        $clip = Get-ClipFile -Directory $WorkDir -BaseName $ClipBase
        if (-not $clip) {
            Fail 'The clip file could not be found after download.'
        }

        $outputPath = Join-Path $WorkDir $OutputName
        Write-Step 'Lowering the audio pitch by one semitone'

        if (Test-FFmpegHasRubberband) {
            & ffmpeg -y -i $clip.FullName -c:v copy -af 'rubberband=pitch=0.943874:formant=preserved' -c:a aac -b:a 192k $outputPath
            if ($LASTEXITCODE -ne 0) {
                throw 'ffmpeg failed while using the rubberband filter.'
            }
        }
        else {
            $sampleRate = Get-AudioSampleRate -InputFile $clip.FullName
            $audioFilter = "asetrate=$sampleRate*0.943874,aresample=$sampleRate,atempo=1.059463"
            & ffmpeg -y -i $clip.FullName -c:v copy -af $audioFilter -c:a aac -b:a 192k $outputPath
            if ($LASTEXITCODE -ne 0) {
                throw 'ffmpeg failed while using the fallback pitch-shift filter chain.'
            }
        }

        Write-Host "Output written to: $outputPath" -ForegroundColor Green
    }
    finally {
        Pop-Location
    }
}

Ensure-Admin

$scriptDir = Get-ScriptDir
$requirementsPath = Join-Path $scriptDir $RequirementsFileName

Write-Step 'Locating Conda'
$script:CondaExe = Get-CondaExe
if (-not $script:CondaExe) {
    Fail 'Conda was not found. Install Miniconda/Anaconda/Miniforge first, or add conda.exe to PATH.'
}
Write-Host "Conda found at: $script:CondaExe" -ForegroundColor Green

Write-Step 'Preparing the Conda environment'
Ensure-CondaEnvironment -SourceEnv $SourceEnvName -TargetEnv $TargetEnvName -PyVersion $PythonVersion
Ensure-PipAndRequirements -TargetEnv $TargetEnvName -RequirementsFile $requirementsPath

Ensure-FFmpegInstalledAndOnPath

Invoke-VideoProcessing -TargetEnv $TargetEnvName -WorkDir $scriptDir -Video $VideoUrl -Start $StartTime -End $EndTime -ClipBase $ClipBaseName -OutputName $OutputFileName

Write-Host "`nAll steps completed successfully." -ForegroundColor Green
