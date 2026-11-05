param([switch]$NoStart, [string]$Ref = 'main')
$ErrorActionPreference = 'Stop'
$etaRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
if ($Ref -ne 'main' -and $Ref -notmatch '^[a-fA-F0-9]{40}$') { throw 'Surum main veya 40 karakterlik commit kimligi olmali.' }
if (-not (Test-Path -LiteralPath (Join-Path $etaRoot 'kurum\EtaControl_KurumPaketi.zip'))) { throw 'Once kurum paketini kurum klasorune kopyalayin.' }
$etaState = Join-Path $etaRoot 'data\server.json'
if (Test-Path -LiteralPath $etaState) {
    $etaServer = Get-Content -LiteralPath $etaState -Raw | ConvertFrom-Json
    if ($etaServer.url -match '^http://127\.0\.0\.1:87[0-9]{2}$') {
        $etaJobs = $null
        try { $etaJobs = Invoke-RestMethod ($etaServer.url + '/api/jobs') -TimeoutSec 5 }
        catch {
            if (-not ($_.Exception -is [Net.WebException] -and $_.Exception.Status -eq [Net.WebExceptionStatus]::ConnectFailure)) { throw 'Calisma durumu okunamadi; uygulamayi kapatip yeniden deneyin.' }
        }
        if ($etaJobs -and $etaJobs.active) { throw 'Terminal islemi suruyor; guncelleme yapilmadi.' }
    }
    $etaPython = Join-Path $etaRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $etaPython)) { throw 'Once uygulamayi kapatin veya KURULUM.ps1 dosyasini calistirin.' }
    & $etaPython -m etacontrol --stop
    if ($LASTEXITCODE -ne 0) { throw 'Uygulama guvenle durdurulamadi.' }
}
$etaGit = Get-Command git.exe -ErrorAction SilentlyContinue
if ($etaGit -and (Test-Path -LiteralPath (Join-Path $etaRoot '.git'))) {
    $etaChanges = & $etaGit.Source -C $etaRoot status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $etaChanges) { throw 'Izlenen kodda yerel degisiklik var; otomatik guncelleme durduruldu.' }
    if ($Ref -eq 'main') {
        & $etaGit.Source -C $etaRoot pull --ff-only origin main
    } else {
        & $etaGit.Source -C $etaRoot fetch origin $Ref
        if ($LASTEXITCODE -ne 0) { throw 'Istenen surum indirilemedi.' }
        & $etaGit.Source -C $etaRoot checkout --detach $Ref
    }
    if ($LASTEXITCODE -ne 0) { throw 'Git guncellemesi tamamlanmadi.' }
    & (Join-Path $etaRoot 'KURULUM.ps1') -NoStart:$NoStart
    exit $LASTEXITCODE
}
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$etaLocal = Join-Path $etaRoot '.yerel'
New-Item -ItemType Directory -Path $etaLocal -Force | Out-Null
$etaDownload = Join-Path $etaLocal ('kaynak-' + [Guid]::NewGuid().ToString('N') + '.zip')
$etaUrl = 'https://codeload.github.com/neyzenburak/EtaControl/zip/' + $Ref
Invoke-WebRequest -Uri $etaUrl -OutFile $etaDownload -UseBasicParsing
Add-Type -AssemblyName System.IO.Compression.FileSystem
$etaArchive = [IO.Compression.ZipFile]::OpenRead($etaDownload)
$etaBackupRoot = Join-Path $etaRoot ('data\guncelleme_yedekleri\' + [Guid]::NewGuid().ToString('N'))
try {
    $etaFiles = @()
    foreach ($etaEntry in $etaArchive.Entries) {
        if ($etaEntry.FullName.EndsWith('/')) { continue }
        $etaParts = $etaEntry.FullName.Split('/')
        if ($etaParts.Length -lt 2) { throw 'Gecersiz kaynak paketi.' }
        $etaRelative = [string]::Join('/', $etaParts[1..($etaParts.Length - 1)])
        if ($etaRelative -match '(^|/)(\.\.|data|\.yerel|\.venv|node_modules|\.git)(/|$)' -or $etaRelative -match ':|\\' -or $etaRelative -match '\.(zip|sqlite3?|db|xls[xm]?|mac)$') { throw 'Kaynak paketinde yasakli yol var.' }
        if ($etaRelative.StartsWith('kurum/') -and $etaRelative -notin @('kurum/README.md', 'kurum/.gitkeep')) { throw 'Kaynak paketi kurum dosyalarini degistiremez.' }
        if ((($etaEntry.ExternalAttributes -shr 16) -band 61440) -eq 40960) { throw 'Kaynak paketi sembolik baglanti iceremez.' }
        $etaDestination = [IO.Path]::GetFullPath((Join-Path $etaRoot $etaRelative))
        if (-not $etaDestination.StartsWith($etaRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Kaynak yolu uygulama disina cikiyor.' }
        $etaFiles += @{ Entry=$etaEntry; Relative=$etaRelative; Destination=$etaDestination }
    }
    foreach ($etaFile in $etaFiles) {
        if (Test-Path -LiteralPath $etaFile.Destination) {
            $etaBackup = Join-Path $etaBackupRoot $etaFile.Relative
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($etaBackup)) -Force | Out-Null
            Copy-Item -LiteralPath $etaFile.Destination -Destination $etaBackup
        }
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($etaFile.Destination)) -Force | Out-Null
        $etaInput = $etaFile.Entry.Open()
        try {
            $etaOutput = [IO.File]::Create($etaFile.Destination)
            try { $etaInput.CopyTo($etaOutput) } finally { $etaOutput.Dispose() }
        } finally { $etaInput.Dispose() }
    }
} finally { $etaArchive.Dispose() }
Write-Host ('Kod yedegi: ' + $etaBackupRoot)
& (Join-Path $etaRoot 'KURULUM.ps1') -NoStart:$NoStart
