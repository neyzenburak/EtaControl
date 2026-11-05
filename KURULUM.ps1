param([switch]$NoStart, [string]$PythonExe = '')
$ErrorActionPreference = 'Stop'
$etaProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
Set-Location -LiteralPath $etaProjectRoot
if (-not (Test-Path -LiteralPath (Join-Path $etaProjectRoot 'kurum\EtaControl_KurumPaketi.zip'))) { throw 'Kurum paketi eksik. EtaControl_KurumPaketi.zip dosyasini kurum klasorune koyun.' }

function Get-EtaPython([string]$candidate) {
    if (-not $candidate -or -not (Test-Path -LiteralPath $candidate) -or $candidate -match 'WindowsApps') { return $null }
    try {
        $details = & $candidate -c "import sys;print(sys.executable if (3,10)<=sys.version_info[:2]<(3,14) else '')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $details) { return $details.Trim() }
    } catch { }
    return $null
}

$etaVenvRoot = Join-Path $etaProjectRoot '.venv'
$etaVenvExe = Join-Path $etaVenvRoot 'Scripts\python.exe'
$etaPython = Get-EtaPython $etaVenvExe
if (-not $etaPython) {
    $etaCandidates = @($PythonExe)
    $etaCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($etaCommand) { $etaCandidates += $etaCommand.Source }
    $etaLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($etaLauncher) {
        foreach ($etaVersion in @('-3.12', '-3.13', '-3.11', '-3.10')) {
            try {
                $etaCandidate = & $etaLauncher.Source $etaVersion -c 'import sys;print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0) { $etaCandidates += $etaCandidate }
            } catch { }
        }
    }
    $etaPythonDirectory = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path -LiteralPath $etaPythonDirectory) {
        $etaCandidates += Get-ChildItem -Path (Join-Path $etaPythonDirectory 'Python*\python.exe') -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
    }
    foreach ($etaCandidate in $etaCandidates) {
        $etaPython = Get-EtaPython $etaCandidate
        if ($etaPython) { break }
    }
    if (-not $etaPython) { throw 'Python 3.10-3.13 bulunamadi. Python 3.12 kuruluysa -PythonExe ile python.exe yolunu belirtin.' }
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
