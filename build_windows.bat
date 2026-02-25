@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion
echo === Nini Windows Build ===
echo.

echo [1/4] Installing dependencies...
pip install -e .[packaging,webr]
if !errorlevel! neq 0 (
    echo [FAIL] pip install failed.
    goto :error
)
echo [1/4] Done.
echo.

echo [1.5/4] Downloading Chromium for kaleido chart export...
set "KALEIDO_CHROME_OK=0"

where kaleido_get_chrome >nul 2>nul
if !errorlevel! equ 0 (
    call kaleido_get_chrome -y
    if !errorlevel! equ 0 (
        set "KALEIDO_CHROME_OK=1"
    )
)

if !KALEIDO_CHROME_OK! neq 1 (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%I"
    if defined PYTHON_EXE (
        for %%I in ("!PYTHON_EXE!") do set "PYTHON_DIR=%%~dpI"
        if exist "!PYTHON_DIR!kaleido_get_chrome.exe" (
            call "!PYTHON_DIR!kaleido_get_chrome.exe" -y
            if !errorlevel! equ 0 (
                set "KALEIDO_CHROME_OK=1"
            )
        )
    )
)

if !KALEIDO_CHROME_OK! neq 1 (
    python -c "from choreographer.cli._cli_utils import get_chrome_sync; print(get_chrome_sync())"
    if !errorlevel! equ 0 (
        set "KALEIDO_CHROME_OK=1"
    )
)

if !KALEIDO_CHROME_OK! neq 1 (
    echo [WARN] Cannot download Chromium automatically. Chart image export may not work in packaged app.
    echo        Try: kaleido_get_chrome -y
    echo        Or : python -c "from choreographer.cli._cli_utils import get_chrome_sync; print(get_chrome_sync())"
)
echo [1.5/4] Done.
echo.

echo [2/4] Building frontend...
pushd web
if !errorlevel! neq 0 (
    echo [FAIL] Cannot enter web directory.
    goto :error
)
call npm install
if !errorlevel! neq 0 (
    popd
    echo [FAIL] npm install failed.
    goto :error
)
call npm run build
if !errorlevel! neq 0 (
    popd
    echo [FAIL] npm run build failed.
    goto :error
)
popd
echo [2/4] Done.
echo.

echo [3/4] Running PyInstaller...
python -m PyInstaller nini.spec --noconfirm
if !errorlevel! neq 0 (
    echo [FAIL] PyInstaller failed.
    goto :error
)
echo [3/4] Done.
echo.

echo [4/4] Creating installer...
where makensis >nul 2>nul
if !errorlevel! equ 0 (
    makensis /INPUTCHARSET UTF8 packaging\installer.nsi
    if !errorlevel! neq 0 (
        echo [WARN] makensis failed, but portable build is still available.
    )
) else (
    echo [SKIP] NSIS not found, skipping installer creation.
    echo        Install from https://nsis.sourceforge.io/ to create setup exe.
)
echo.

echo === Build complete! ===
echo Portable: dist\nini\nini.exe
echo Installer: dist\Nini-0.1.0-Setup.exe (if NSIS available)
endlocal
goto :eof

:error
echo.
echo === Build failed! ===
endlocal
exit /b 1
