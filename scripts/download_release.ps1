param(
    [string]$OutputDirectory,
    [string]$LocalPartsDirectory,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$archiveName = 'tax-exam-skill-1.2.0-windows-x64-private.zip'
$baseUrl = 'https://github.com/yuanxushi111-bot/-1/releases/download/v1.2.0/'

function Receive-File([string]$Name, [string]$Target) {
    if ($LocalPartsDirectory) {
        Copy-Item -LiteralPath (Join-Path $LocalPartsDirectory $Name) -Destination $Target -Force
        return
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri ($baseUrl + $Name) -OutFile $Target -TimeoutSec 600
            return
        } catch {
            if ($attempt -eq 3) { throw }
            Write-Host ('Retrying download: ' + $Name)
            Start-Sleep -Seconds 2
        }
    }
}

function Test-File([string]$Path, [long]$Length, [string]$Hash) {
    return ((Test-Path -LiteralPath $Path -PathType Leaf) -and
        (Get-Item -LiteralPath $Path).Length -eq $Length -and
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $Hash)
}

try {
    if (-not $OutputDirectory) {
        if ($env:TAX_EXAM_DOWNLOAD_SELF) {
            $OutputDirectory = Split-Path -Parent $env:TAX_EXAM_DOWNLOAD_SELF
        } else {
            $OutputDirectory = $PSScriptRoot
        }
    }
    $destination = [IO.Path]::GetFullPath($OutputDirectory)
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $work = Join-Path $destination '.tax-exam-v1.2.0-parts'
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $manifestPath = Join-Path $work 'split-manifest.json'
    $checksumPath = Join-Path $work ($archiveName.Replace('.zip', '.sha256.json'))
    Receive-File 'split-manifest.json' $manifestPath
    Receive-File ($archiveName.Replace('.zip', '.sha256.json')) $checksumPath
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $checksum = Get-Content -LiteralPath $checksumPath -Raw | ConvertFrom-Json
    if ($manifest.version -ne '1.2.0' -or $manifest.archive -ne $archiveName -or
        $checksum.file -ne $archiveName -or $manifest.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or
        $manifest.sha256 -ne $checksum.sha256 -or $manifest.bytes -ne $checksum.bytes -or
        $manifest.bytes -le 0 -or $manifest.parts.Count -lt 1 -or $manifest.parts.Count -gt 99) {
        throw 'Invalid release metadata. No archive was created.'
    }
    $total = [long]0
    $number = 0
    foreach ($part in $manifest.parts) {
        $number++
        $expectedName = $archiveName + ('.{0:D3}' -f $number)
        if ($part.file -ne $expectedName -or $part.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or
            $part.bytes -le 0 -or $part.bytes -gt 67108864) {
            throw 'Invalid part name, size or hash.'
        }
        $total += [long]$part.bytes
    }
    if ($total -ne $manifest.bytes) { throw 'Part sizes do not match archive size.' }
    $archive = Join-Path $destination $archiveName
    if (-not (Test-File $archive $manifest.bytes $manifest.sha256)) {
        foreach ($part in $manifest.parts) {
            $partPath = Join-Path $work $part.file
            if (-not (Test-File $partPath $part.bytes $part.sha256)) {
                Write-Host ('Downloading ' + $part.file)
                $temporary = $partPath + '.partial'
                Receive-File $part.file $temporary
                if (-not (Test-File $temporary $part.bytes $part.sha256)) {
                    throw ('SHA-256 check failed: ' + $part.file)
                }
                Move-Item -LiteralPath $temporary -Destination $partPath -Force
            } else {
                Write-Host ('Reusing verified part: ' + $part.file)
            }
        }
        $temporaryArchive = $archive + '.partial'
        $output = [IO.File]::Create($temporaryArchive)
        try {
            foreach ($part in $manifest.parts) {
                $inputFile = [IO.File]::OpenRead((Join-Path $work $part.file))
                try { $inputFile.CopyTo($output) } finally { $inputFile.Dispose() }
            }
        } finally { $output.Dispose() }
        if (-not (Test-File $temporaryArchive $manifest.bytes $manifest.sha256)) {
            throw 'The merged ZIP failed its SHA-256 check.'
        }
        Move-Item -LiteralPath $temporaryArchive -Destination $archive -Force
    }
    Write-Host ('Verified complete ZIP: ' + $archive)
    Write-Host 'Extract it into a NEW folder, then run the installation check CMD.'
    Write-Host 'This downloader does not upload learning records or run the installed agent.'
    if (-not $NoPause) { Read-Host 'Press Enter to close' | Out-Null }
    exit 0
} catch {
    Write-Host ('Download failed: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Verified parts are retained. Run this downloader again to resume.'
    if (-not $NoPause) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
