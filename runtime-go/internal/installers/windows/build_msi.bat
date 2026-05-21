@echo off
REM Build script for AgentOS Windows MSI Installer
REM Usage: build_msi.bat [version] [sign]

setlocal enabledelayedexpansion

set VERSION=%1
if "%VERSION%"=="" set VERSION=0.1.0

set SIGN=%2
set SOURCE_DIR=%~dp0
set BUILD_DIR=%TEMP%\agentos-wix-build-%RANDOM%

echo Building AgentOS Windows Installer v%VERSION%
echo ===========================================

REM Check prerequisites
if not exist "%ProgramFiles(x86)%\WiX Toolset v3.11\bin\candle.exe" (
    echo ERROR: WiX Toolset v3.11 not found.
    echo Please install from: https://wixtoolset.org/
    exit /b 1
)

REM Set WiX path
set WIX_PATH=%ProgramFiles(x86)%\WiX Toolset v3.11\bin
set PATH=%WIX_PATH%;%PATH%

REM Create build directory
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
mkdir "%BUILD_DIR%" >nul

echo.
echo Compiling WiX source files...

REM Compile WiX files
candle.exe "%SOURCE_DIR%Product.wxs" "%SOURCE_DIR%Components.wxs" ^
    -dSourceDir="%SOURCE_DIR%" ^
    -dVersion="%VERSION%" ^
    -out "%BUILD_DIR%\" ^
    -ext WixUIExtension ^
    -nologo

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: WiX compilation failed
    exit /b 1
)

echo Linking MSI...

REM Link MSI
candle.exe "%SOURCE_DIR%Bundle.wxs" ^
    -dSourceDir="%SOURCE_DIR%" ^
    -dVersion="%VERSION%" ^
    -out "%BUILD_DIR%\" ^
    -nologo

light.exe "%BUILD_DIR%Product.wixobj" "%BUILD_DIR%Components.wixobj" "%BUILD_DIR%Bundle.wixobj" ^
    -o "%SOURCE_DIR%AgentOS-v%VERSION%.msi" ^
    -ext WixUIExtension ^
    -sice:ICE27 ^
    -nologo

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: WiX linking failed
    exit /b 1
)

REM Sign the MSI if requested
if "%SIGN%"=="sign" (
    echo.
    echo Signing MSI...
    
    set SIGNTOOL_PATH=%ProgramFiles(x86)%\Windows Kits\10\bin\10.0.22000.0\x64\signtool.exe
    if not exist "%SIGNTOOL_PATH%" set SIGNTOOL_PATH=%ProgramFiles%\Windows Kits\10\bin\10.0.22000.0\x64\signtool.exe
    if not exist "%SIGNTOOL_PATH%" set SIGNTOOL_PATH=signtool.exe
    
    if exist "%SOURCE_DIR%certificate.pfx" (
        "%SIGNTOOL_PATH%" sign /f "%SOURCE_DIR%certificate.pfx" /p "%CERT_PASSWORD%" /t http://timestamp.digicert.com /d "AgentOS" "%SOURCE_DIR%AgentOS-v%VERSION%.msi"
        if %ERRORLEVEL% EQU 0 (
            echo MSI signed successfully
        ) else (
            echo WARNING: Signing failed, continuing with unsigned MSI
        )
    ) else (
        echo WARNING: Certificate not found at %SOURCE_DIR%certificate.pfx, skipping signing
    )
)

REM Cleanup
rmdir /s /q "%BUILD_DIR%"

REM Get file size
for %%I in ("%SOURCE_DIR%AgentOS-v%VERSION%.msi") do set SIZE=%%~zI
set /a SIZE_MB=SIZE/1048576

echo.
echo ===========================================
echo Build complete: AgentOS-v%VERSION%.msi
echo Size: %SIZE_MB% MB
echo ===========================================
echo.
echo To install:
echo   msiexec /i AgentOS-v%VERSION%.msi /qb
echo.
echo To install with options:
echo   msiexec /i AgentOS-v%VERSION%.msi INSTALLDIR="C:\AgentOS" /qb

endlocal
exit /b 0