param([switch]$NoStart, [string]$PythonExe = '', [switch]$PythonTani)
$ErrorActionPreference = 'Stop'
$etaProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
Set-Location -LiteralPath $etaProjectRoot
$script:etaPythonDiagnostics = @()

function Add-EtaPythonDiagnostic([string]$candidate, [string]$message) {
    $etaMessage = ($message -replace '\s+', ' ').Trim()
    if ($etaMessage.Length -gt 400) { $etaMessage = $etaMessage.Substring(0,400) }
    $script:etaPythonDiagnostics += ($candidate + ' -> ' + $etaMessage)
}

function Get-EtaStorePackages {
    if ($null -eq $script:etaStorePackages) {
        $script:etaStorePackages = @()
        if (Get-Command Get-AppxPackage -ErrorAction SilentlyContinue) {
            try { $script:etaStorePackages = @(Get-AppxPackage -Name 'PythonSoftwareFoundation.Python*' -ErrorAction Stop) }
            catch { Add-EtaPythonDiagnostic 'Store paket listesi' $_.Exception.Message }
        }
    }
    return $script:etaStorePackages
}

function Get-EtaPython([string]$candidate, [string[]]$prefix = @()) {
    if (-not $candidate) { return $null }
    # Probe aliases with arguments, even if Appx enumeration is unavailable.
    # Microsoft's download stub returns an error with arguments; it is not Python.
    $etaProbe = $null
    try {
        $etaInfo = New-Object System.Diagnostics.ProcessStartInfo
        $etaInfo.FileName = $candidate
        $etaInfo.Arguments = (($prefix -join ' ') + ' -I -c "import sys,json;print(json.dumps(dict(executable=sys.executable,version=sys.version.split()[0],supported=(3,10)<=sys.version_info[:2]<(3,15))))"').Trim()
        $etaInfo.UseShellExecute = $false
        $etaInfo.CreateNoWindow = $true
        $etaInfo.RedirectStandardOutput = $true
        $etaInfo.RedirectStandardError = $true
        $etaProbe = [System.Diagnostics.Process]::Start($etaInfo)
        $etaOutput = $etaProbe.StandardOutput.ReadToEndAsync()
        $etaErrors = $etaProbe.StandardError.ReadToEndAsync()
        if (-not $etaProbe.WaitForExit(8000)) { $etaProbe.Kill(); $etaProbe.WaitForExit(); Add-EtaPythonDiagnostic $candidate '8 saniyede yanit vermedi'; return $null }
        if ($etaProbe.ExitCode -ne 0) { Add-EtaPythonDiagnostic $candidate ('Cikis kodu ' + $etaProbe.ExitCode + ': ' + $etaErrors.Result); return $null }
        $etaDetails = $etaOutput.Result | ConvertFrom-Json
        if ($etaDetails.supported -eq $true -and $etaDetails.executable -is [string] -and $etaDetails.executable.Trim()) {
            Add-EtaPythonDiagnostic $candidate ('Uygun Python ' + $etaDetails.version)
            if (-not $prefix.Count) { return $candidate }
            return $etaDetails.executable.Trim()
        }
        Add-EtaPythonDiagnostic $candidate ('Desteklenmeyen surum: ' + $etaDetails.version + '. Gerekli: 3.10-3.14')
    } catch { Add-EtaPythonDiagnostic $candidate $_.Exception.Message }
    finally { if ($etaProbe) { $etaProbe.Dispose() } }
    return $null
}

function Find-EtaPython([string]$explicitPath) {
    $etaFound = Get-EtaPython $explicitPath
    if ($etaFound) { return $etaFound }
    # Try all PATH matches, including version-specific Store aliases.
    $etaNames = @('python.exe', 'python3.exe', 'python3.12.exe', 'python3.13.exe', 'python3.11.exe', 'python3.10.exe', 'python3.14.exe', 'python3.15.exe')
    foreach ($etaCommand in @(Get-Command -Name $etaNames -All -CommandType Application -ErrorAction SilentlyContinue)) {
        $etaFound = Get-EtaPython $etaCommand.Source
        if ($etaFound) { return $etaFound }
    }
    foreach ($etaLauncher in @(Get-Command py.exe -All -CommandType Application -ErrorAction SilentlyContinue)) {
        foreach ($etaVersion in @('-3.12', '-3.13', '-3.14', '-3.11', '-3.10')) {
            $etaFound = Get-EtaPython $etaLauncher.Source @($etaVersion)
            if ($etaFound) { return $etaFound }
        }
        $etaFound = Get-EtaPython $etaLauncher.Source
        if ($etaFound) { return $etaFound }
    }
    $etaCandidates = @()
    foreach ($etaName in $etaNames) {
        $etaCandidates += Join-Path (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps') $etaName
        $etaCandidates += Join-Path (Join-Path $env:LOCALAPPDATA 'Python\bin') $etaName
    }
    $etaPythonDirectory = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path -LiteralPath $etaPythonDirectory) {
        $etaCandidates += @(Get-ChildItem -Path (Join-Path $etaPythonDirectory 'Python*\python.exe') -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
    $etaPackageAliases = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\PythonSoftwareFoundation.Python*\python*.exe'
    $etaCandidates += @(Get-ChildItem -Path $etaPackageAliases -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    foreach ($etaPackage in @(Get-EtaStorePackages)) {
        # Package aliases also work when WindowsApps is missing from PATH.
        foreach ($etaName in $etaNames) {
            if ($etaPackage.InstallLocation) { $etaCandidates += Join-Path $etaPackage.InstallLocation $etaName }
            if ($etaPackage.PackageFamilyName) {
                $etaCandidates += Join-Path (Join-Path (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps') $etaPackage.PackageFamilyName) $etaName
            }
        }
    }
    foreach ($etaCandidate in ($etaCandidates | Select-Object -Unique)) {
        $etaFound = Get-EtaPython $etaCandidate
        if ($etaFound) { return $etaFound }
    }
    return $null
}

if ($PythonTani) {
    $etaDiagnosticPython = Find-EtaPython $PythonExe
    $script:etaPythonDiagnostics | ForEach-Object { Write-Host $_ }
    if ($etaDiagnosticPython) { Write-Host ('Secilen Python: ' + $etaDiagnosticPython) }
    else { Write-Host 'Uygun Python bulunamadi. Yukaridaki tani ciktisini destek icin paylasin.' }
    return
}
if (-not (Test-Path -LiteralPath (Join-Path $etaProjectRoot 'kurum\EtaControl_KurumPaketi.zip'))) { throw 'Kurum paketi eksik. EtaControl_KurumPaketi.zip dosyasini kurum klasorune koyun.' }

$etaVenvRoot = Join-Path $etaProjectRoot '.venv'
$etaVenvExe = Join-Path $etaVenvRoot 'Scripts\python.exe'
$etaPython = Get-EtaPython $etaVenvExe
if (-not $etaPython) {
    $etaPython = Find-EtaPython $PythonExe
    if (-not $etaPython) {
        $script:etaPythonDiagnostics | ForEach-Object { Write-Host $_ }
        throw 'Python 3.10-3.14 bulunamadi. Tani icin KURULUM.ps1 -PythonTani calistirin. Python 3.15 ve ustu bu surumde desteklenmiyor.'
    }
    if (Test-Path -LiteralPath $etaVenvRoot) {
        $etaResolvedVenv = [System.IO.Path]::GetFullPath($etaVenvRoot)
        if ($etaResolvedVenv -ne (Join-Path $etaProjectRoot '.venv') -or ((Get-Item -LiteralPath $etaVenvRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Sanal ortam yolu guvenle yeniden adlandirilamadi.'
        }
        Rename-Item -LiteralPath $etaVenvRoot -NewName ('.venv_eski_' + [Guid]::NewGuid().ToString('N').Substring(0,8))
    }
    Write-Host 'Projeye ozel Python ortami olusturuluyor...'
    & $etaPython -m venv $etaVenvRoot
    if ($LASTEXITCODE -ne 0) { throw 'Python sanal ortami olusturulamadi.' }
}

Write-Host 'Python paketleri kuruluyor (internet/proxy erisimi gerekir)...'
& $etaVenvExe -m pip install --disable-pip-version-check -r (Join-Path $etaProjectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python paketleri kurulamadi. Pip ciktisindaki internet/proxy veya yetki hatasini kontrol edin.' }

$etaServerState = Join-Path $etaProjectRoot 'data\server.json'
if (Test-Path -LiteralPath $etaServerState) {
    $etaServer = Get-Content -LiteralPath $etaServerState -Raw | ConvertFrom-Json
    if ($etaServer.url -match '^http://127\.0\.0\.1:87[0-9]{2}$') {
        $etaJobs = $null
        try { $etaJobs = Invoke-RestMethod ($etaServer.url + '/api/jobs') -TimeoutSec 5 }
        catch {
            if (-not ($_.Exception -is [System.Net.WebException] -and $_.Exception.Status -eq [System.Net.WebExceptionStatus]::ConnectFailure)) {
                throw 'Uygulamanin calisma durumu okunamadi. Uygulamayi kapatip kurulumu yeniden calistirin.'
            }
        }
        if ($etaJobs -and $etaJobs.active) { throw 'Terminal islemi suruyor. Bitmesini bekleyin; kurulum veri cekimini durdurmadi.' }
    }
    & $etaVenvExe -m etacontrol --stop
    if ($LASTEXITCODE -ne 0) { throw 'Mevcut uygulama guvenle durdurulamadi.' }
}

Write-Host 'Iki Excel cikti yolu test ediliyor; terminal ve veritabani kullanilmaz...'
& $etaVenvExe -m etacontrol --check
if ($LASTEXITCODE -ne 0) { throw 'Excel veya uygulama bagimlilik testi gecmedi. Kurulum tamamlanmadi.' }
$etaRuntimePath = Join-Path $etaProjectRoot 'runtime.json'
if (Test-Path -LiteralPath $etaRuntimePath) {
    $etaBackupDirectory = Join-Path $etaProjectRoot ('data\setup_backups\' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $etaBackupDirectory -Force | Out-Null
    Copy-Item -LiteralPath $etaRuntimePath -Destination (Join-Path $etaBackupDirectory 'runtime.json')
}
$etaRuntime = @{ python = $etaVenvExe; excel_engine = 'python_openpyxl'; portable_version = 1 }
[System.IO.File]::WriteAllText($etaRuntimePath, ($etaRuntime | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
Write-Host 'Kurulum ve Excel testleri tamamlandi. Node.js ve masaustu Excel kurulumu gerekmez.'
Write-Host ('Uygulama klasoru: ' + $etaProjectRoot)
if (-not $NoStart) { & $etaVenvExe -m etacontrol }
