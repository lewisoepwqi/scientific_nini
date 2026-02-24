@echo off
chcp 65001 >nul 2>nul
echo === Nini Windows Build ===
echo.

echo [1/4] Installing dependencies...
pip install -e .[packaging]
if %errorlevel% neq 0 goto :error

echo [2/4] Building frontend...
cd web && npm install && npm run build && cd ..
if %errorlevel% neq 0 goto :error

echo [3/4] Running PyInstaller...
pyinstaller nini.spec --noconfirm
if %errorlevel% neq 0 goto :error

echo [4/4] Creating installer...
where makensis >nul 2>nul
if %errorlevel% equ 0 (
    makensis packaging\installer.nsi
) else (
    echo NSIS not found, skipping installer creation.
    echo Install from https://nsis.sourceforge.io/ to create setup exe.
)

echo.
echo === Build complete! ===
echo Portable: dist\nini\nini.exe
echo Installer: dist\Nini-0.1.0-Setup.exe (if NSIS available)
goto :eof

:error
echo Build failed with error %errorlevel%
exit /b %errorlevel%
