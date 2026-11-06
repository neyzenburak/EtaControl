param([Parameter(Mandatory=$true)][string]$PythonExe)
$ErrorActionPreference = 'Stop'
$etaRepo = Split-Path -Parent $PSScriptRoot
$etaTokens = $null
$etaErrors = $null
$etaAst = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $etaRepo 'KURULUM.ps1'), [ref]$etaTokens, [ref]$etaErrors)
if ($etaErrors.Count) { throw 'Kurulum PowerShell sozdizimi gecersiz.' }
foreach ($etaFunction in $etaAst.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst]}, $false)) {
    . ([scriptblock]::Create($etaFunction.Extent.Text))
}
function Assert-Eta($condition, $message) { if (-not $condition) { throw $message } }
$etaRealPython = Get-EtaPython $PythonExe
Assert-Eta ([bool]$etaRealPython) 'Gercek Python bulunamadi.'
Assert-Eta (-not (Get-EtaPython (Join-Path $env:TEMP 'eta-missing-python.exe'))) 'Olmayan exe kabul edildi.'
$etaTestRoot = Join-Path $env:TEMP ('eta-python-test-' + [Guid]::NewGuid().ToString('N'))
$etaTestVenv = Join-Path $etaTestRoot 'WindowsApps\Store Python test'
$etaOriginalLocal = $env:LOCALAPPDATA
try {
    & $etaRealPython -m venv $etaTestVenv
    if ($LASTEXITCODE -ne 0) { throw 'Ornek Python ortami olusturulamadi.' }
    $etaStorePython = Join-Path $etaTestVenv 'Scripts\python.exe'
    Assert-Eta ([bool](Get-EtaPython $etaStorePython)) 'WindowsApps icindeki calisan Python reddedildi.'
    # Isolate PATH and python.org discovery: emulate an Appx registration whose
    # working interpreter is not on PATH. The probe still starts a real Python.
    $env:LOCALAPPDATA = Join-Path $etaTestRoot 'local'
    $script:etaStorePackages = @([pscustomobject]@{InstallLocation=(Join-Path $etaTestVenv 'Scripts');PackageFamilyName=''})
    function Get-Command { param($Name, [switch]$All, $CommandType, $ErrorAction) return $null }
    $etaDiscovered = Find-EtaPython ''
    Assert-Eta ($etaDiscovered -ieq $etaStorePython) 'PATH disindaki kayitli Store paketi bulunamadi.'
    Remove-Item Function:\Get-Command
    # An unregistered root alias must not be launched: it may open the Store.
    $script:etaStorePackages = @()
    $etaStub = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\python.exe'
    Assert-Eta (-not (Get-EtaPython $etaStub)) 'Kurulu paket olmadan Store yonlendirmesi kabul edildi.'
    Write-Host 'Python kesfi: gercek yorumlayici, WindowsApps yolu, PATH disi Store kaydi ve bos alias kontrolleri gecti.'
} finally {
    if (Test-Path Function:\Get-Command) { Remove-Item Function:\Get-Command }
    $env:LOCALAPPDATA = $etaOriginalLocal
    # Only this newly-created, resolved test tree is eligible for cleanup.
    $etaResolvedTest = [IO.Path]::GetFullPath($etaTestRoot)
    $etaResolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    if ($etaResolvedTest.StartsWith($etaResolvedTemp, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $etaResolvedTest) -like 'eta-python-test-*') {
        Remove-Item -LiteralPath $etaResolvedTest -Recurse -Force -ErrorAction SilentlyContinue
    }
}
