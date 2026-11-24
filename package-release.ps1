# Run build.ps1 first. The installer and any volume files are written to build/release.
# Use -Split to go directly to disk spanning when a large payload is expected.
param([switch]$Split)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$buildRoot = Join-Path $PSScriptRoot "build"
$cacheRoot = Join-Path $buildRoot "tools"
$releaseRoot = Join-Path $buildRoot "release"
$payload = Join-Path $PSScriptRoot "dist\DemucsStudio"
$scriptPath = Join-Path $PSScriptRoot "packaging\DemucsStudio.iss"
$installerName = "DemucsStudio-Setup-x64.exe"
$onlineName = "DemucsStudio-OnlineSetup-x64.exe"
$installerPattern = '^DemucsStudio-Setup-x64(?:-[1-9][0-9]*\.bin|\.exe)$'
if (!(Test-Path -LiteralPath (Join-Path $payload "DemucsStudio.exe") -PathType Leaf)) {
    throw "Build the Windows application with build.ps1 before packaging."
}
$versionSource = Get-Content -Encoding utf8 -Raw -LiteralPath (Join-Path $PSScriptRoot "demucs_gui\version.py")
if ($versionSource -notmatch '(?m)^VERSION\s*=\s*["''](\d+\.\d+\.\d+)["'']\s*$') {
    throw "Expected a numeric X.Y.Z VERSION in demucs_gui/version.py."
}
$appVersion = $Matches[1]
if ($versionSource -notmatch '(?m)^REPO_URL\s*=\s*["''](https://github\.com/[\w.-]+/[\w.-]+)["'']\s*$') {
    throw "Expected a GitHub REPO_URL in demucs_gui/version.py."
}
$assetBase = "$($Matches[1])/releases/download/v$appVersion"
[IO.Directory]::CreateDirectory($cacheRoot) | Out-Null

function Confirm-InnoPublisher([string]$file) {
    $signature = Get-AuthenticodeSignature -FilePath $file
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(?:^|, )CN=Pyrsys B\.V\.(?:,|$)') {
        throw "Inno Setup publisher verification failed for $file"
    }
}

function Get-InnoCompiler {
    # Official redistributable is installed in its documented /PORTABLE mode.
    $compilerRoot = Join-Path $cacheRoot 'inno-7.1.1'
    $compiler = Join-Path $compilerRoot 'ISCC.exe'
    if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) {
        $bootstrap = Join-Path $cacheRoot 'innosetup-7.1.1-x64.exe'
        $download = 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe'
        if (!(Test-Path -LiteralPath $bootstrap -PathType Leaf)) {
            $partial = "$bootstrap.download"
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $download -OutFile $partial
                Move-Item -LiteralPath $partial -Destination $bootstrap
            } finally {
                if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial }
            }
        }
        $expected = '8A5A6711C3766A6E5FB74F280BA0E3551E719CE94538D901FDBD1F8F9920B3F0'
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $bootstrap).Hash -ne $expected) {
            throw "The cached Inno Setup 7.1.1 installer failed its SHA-256 check: $bootstrap"
        }
        Confirm-InnoPublisher $bootstrap
        $flags = @('/PORTABLE=1', '/CURRENTUSER', '/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES',
                   '/NORESTART', '/NOICONS', ('/DIR="' + $compilerRoot + '"'))
        $install = Start-Process -FilePath $bootstrap -ArgumentList $flags -WindowStyle Hidden -PassThru -Wait
        if ($install.ExitCode -ne 0) { throw "Inno Setup compiler setup failed ($($install.ExitCode))." }
    }
    Confirm-InnoPublisher $compiler
    return $compiler
}

function Invoke-InnoCompiler([string[]]$compilerArgs) {
    # Windows may briefly lock setup.exe while its icon/version resources are updated.
    $ErrorActionPreference = 'Continue'
    for ($attempt = 1; $attempt -le 4; $attempt++) {
        $log = (& $compilerPath @compilerArgs 2>&1 | Out-String)
        if ($LASTEXITCODE -eq 0) { return }
        if ($log -notmatch 'EndUpdateResource failed|output file is in use' -or $attempt -eq 4) {
            throw "Inno Setup compilation failed ($LASTEXITCODE). $log"
        }
        Start-Sleep -Seconds $attempt
    }
}

function Build-Installer([string]$output, [bool]$spanning) {
    [IO.Directory]::CreateDirectory($output) | Out-Null
    $flags = @('--quiet', "--output-dir=$output", "--define=AppVersion=$appVersion", "--define=Payload=$payload")
    if ($spanning) { $flags += '--define=Split' }
    Invoke-InnoCompiler ($flags + $scriptPath)
}

function Build-OnlineInstaller([string]$output, [IO.FileInfo[]]$offlineAssets) {
    $entries = foreach ($part in $offlineAssets) {
        $digest = (Get-FileHash -LiteralPath $part.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "DownloadPage.Add('$assetBase/$($part.Name)', '$($part.Name)', '$digest');"
    }
    $include = Join-Path $output 'download-entries.iss'
    [IO.File]::WriteAllLines($include, [string[]]$entries, [Text.Encoding]::ASCII)
    $onlineScript = Join-Path $PSScriptRoot 'packaging\DemucsStudioOnline.iss'
    Invoke-InnoCompiler @('--quiet', "--output-dir=$output", "--define=AppVersion=$appVersion",
                          "--define=DownloadEntries=$include", $onlineScript)
}

$buildLock = [IO.File]::Open((Join-Path $buildRoot "release-packaging.lock"), 'OpenOrCreate', 'Write', 'None')
$stage = Join-Path $buildRoot ("pkg-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
try {
    $compilerPath = Get-InnoCompiler
    Build-Installer $stage $Split.IsPresent
    $stagedExe = Join-Path $stage $installerName
    if ((Get-Item -LiteralPath $stagedExe).Length -ge 2GB -and !$Split) {
        Write-Host "Compressed setup exceeds the release asset limit. Building volumes."
        Build-Installer $stage $true
    }
    $artifacts = @(Get-ChildItem -LiteralPath $stage -File | Where-Object Name -match $installerPattern)
    if ($artifacts.Count -eq 0 -or ($artifacts | Where-Object Length -ge 2GB)) {
        throw "The installer output is missing or exceeds the 2 GiB release asset limit."
    }
    if ($artifacts.Count -gt 1) {
        Build-OnlineInstaller $stage $artifacts
        $artifacts += Get-Item -LiteralPath (Join-Path $stage $onlineName)
    }
    [IO.Directory]::CreateDirectory($releaseRoot) | Out-Null
    foreach ($asset in $artifacts) {
        Copy-Item -LiteralPath $asset.FullName -Destination (Join-Path $releaseRoot $asset.Name) -Force
    }
    # An earlier large build may have left extra volumes in this output directory.
    Get-ChildItem -LiteralPath $releaseRoot -File | Where-Object {
        ($_.Name -match $installerPattern -or $_.Name -eq $onlineName) -and $_.Name -notin $artifacts.Name
    } | ForEach-Object { Remove-Item -LiteralPath $_.FullName }
    Get-ChildItem -LiteralPath $releaseRoot -File | Where-Object Name -in $artifacts.Name |
        Select-Object Name, Length
} finally {
    $buildLock.Dispose()
    if (Test-Path -LiteralPath $stage) {
        $parent = Split-Path -Parent (Resolve-Path -LiteralPath $stage).Path
        if ($parent -eq (Resolve-Path -LiteralPath $buildRoot).Path -and (Split-Path -Leaf $stage) -match '^pkg-[0-9a-f]{8}$') {
            Remove-Item -Recurse -LiteralPath $stage -Force
        }
    }
}
