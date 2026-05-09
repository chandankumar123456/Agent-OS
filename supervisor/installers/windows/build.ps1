# Build script for AgentOS Windows Installer
param(
    [string]$Version = "0.1.0",
    [string]$SourceDir = ".",
    [switch]$Sign,
    [string]$CertificatePath = "",
    [string]$CertificatePassword = ""
)

$ErrorActionPreference = "Stop"

Write-Host "Building AgentOS Windows Installer v$Version" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Check if WiX is installed
$wixPath = Join-Path ${env:ProgramFiles(x86)} "WiX Toolset v3.11\bin"
if (!(Test-Path $wixPath)) {
    $wixPath = Join-Path $env:ProgramFiles "WiX Toolset v3.11\bin"
}
if (!(Test-Path $wixPath)) {
    Write-Error "WiX Toolset not found. Please install WiX from https://wixtoolset.org/"
    exit 1
}

$env:PATH = "$wixPath;$env:PATH"

# Check for required files
$requiredFiles = @(
    "..\..\supervisor.exe",
    "..\..\config\default.yaml",
    "..\..\..\assets\icons\agentos.ico",
    "LICENSE.rtf"
)

foreach ($file in $requiredFiles) {
    $fullPath = Join-Path $SourceDir $file
    if (!(Test-Path $fullPath)) {
        Write-Warning "Missing file: $file"
    }
}

# Create temporary directory for build
$buildDir = Join-Path $env:TEMP "agentos-wix-build"
if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir
}
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

Write-Host "`nCompiling WiX source files..." -ForegroundColor Yellow

# Compile WiX files
& candle.exe `"$SourceDir\Product.wxs`" `"$SourceDir\Components.wxs`" `
    -dSourceDir=`"$SourceDir`" `
    -dVersion=`"$Version`" `
    -out `"$buildDir\`" `
    -ext WixUIExtension `
    -nologo

if ($LASTEXITCODE -ne 0) {
    Write-Error "WiX compilation failed"
    exit 1
}

Write-Host "Linking MSI..." -ForegroundColor Yellow

# Link MSI
$outputName = "AgentOS-v$Version.msi"
& light.exe `"$buildDir\Product.wixobj`" `"$buildDir\Components.wixobj`" `
    -o `"$SourceDir\$outputName`" `
    -ext WixUIExtension `
    -sice:ICE27 `
    -nologo

if ($LASTEXITCODE -ne 0) {
    Write-Error "WiX linking failed"
    exit 1
}

# Sign the MSI if requested
if ($Sign) {
    Write-Host "`nSigning MSI..." -ForegroundColor Yellow
    
    if (!(Test-Path $CertificatePath)) {
        Write-Warning "Certificate not found at $CertificatePath, skipping signing"
    } else {
        $signtoolPath = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin\10.0.22000.0\x64\signtool.exe"
        if (!(Test-Path $signtoolPath)) {
            $signtoolPath = "signtool.exe"
        }
        
        & $signtoolPath sign `
            /f `"$CertificatePath`" `
            /p `"$CertificatePassword`" `
            /t http://timestamp.digicert.com `
            /d "AgentOS" `
            /du "https://agentos.dev" `
            `"$SourceDir\$outputName`"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "MSI signed successfully" -ForegroundColor Green
        } else {
            Write-Warning "Signing failed, continuing with unsigned MSI"
        }
    }
}

# Cleanup
Remove-Item -Recurse -Force $buildDir

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "Build complete: $outputName" -ForegroundColor Green
Write-Host "Size: $([math]::Round((Get-Item "$SourceDir\$outputName").Length / 1MB, 2)) MB" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
