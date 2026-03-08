@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion
echo === Nini Windows Build ===
echo.

for /f "usebackq delims=" %%I in (`python -c "import pathlib, re; text=pathlib.Path('pyproject.toml').read_text(encoding='utf-8'); m=re.search(r'^version\\s*=\\s*\"([^\"]+)\"', text, re.M); print(m.group(1) if m else '0.1.0')"` ) do set "NINI_VERSION=%%I"
if not defined NINI_VERSION set "NINI_VERSION=0.1.0"

set "GENERATED_SECRET_FILE=src\nini\_builtin_key.py"
set "GENERATED_SECRET=0"

echo [1/4] Installing dependencies...
pip install -e .[packaging,webr]
if !errorlevel! neq 0 (
    echo [FAIL] pip install failed.
    goto :error
)
echo [1/4] Done.
echo.

echo [1.2/4] Preparing packaged secrets...
if defined NINI_BUILTIN_DASHSCOPE_API_KEY (
    set "HAS_PACKAGED_SECRET=1"
)
if defined NINI_TRIAL_API_KEY (
    set "HAS_PACKAGED_SECRET=1"
)
if defined HAS_PACKAGED_SECRET (
    python scripts\encrypt_builtin_key.py
    if !errorlevel! neq 0 (
        echo [FAIL] Secret generation failed.
        goto :error
    )
    set "GENERATED_SECRET=1"
) else (
    echo [SKIP] No packaged secret configured. Set NINI_BUILTIN_DASHSCOPE_API_KEY and/or NINI_TRIAL_API_KEY to embed trial credentials.
)
echo [1.2/4] Done.
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

echo [1.8/4] Checking optional local-model bundle inputs...
if defined NINI_OLLAMA_BUNDLE_DIR (
    echo [INFO] NINI_OLLAMA_BUNDLE_DIR=!NINI_OLLAMA_BUNDLE_DIR!
) else (
    echo [INFO] NINI_OLLAMA_BUNDLE_DIR not set. Portable Ollama runtime will not be bundled.
)
if defined NINI_OLLAMA_MODELS_DIR (
    echo [INFO] NINI_OLLAMA_MODELS_DIR=!NINI_OLLAMA_MODELS_DIR!
) else (
    echo [INFO] NINI_OLLAMA_MODELS_DIR not set. Ollama model weights will not be bundled.
)
echo [1.8/4] Done.
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
    makensis /INPUTCHARSET UTF8 /DPRODUCT_VERSION=!NINI_VERSION! packaging\installer.nsi
    if !errorlevel! neq 0 (
        echo [WARN] makensis failed, but portable build is still available.
    )
) else (
    echo [SKIP] NSIS not found, skipping installer creation.
    echo        Install from https://nsis.sourceforge.io/ to create setup exe.
)
echo.

echo === Build complete! ===
echo GUI Launcher: dist\nini\nini.exe
echo CLI Entry : dist\nini\nini-cli.exe
echo Installer : dist\Nini-!NINI_VERSION!-Setup.exe (if NSIS available)
if !GENERATED_SECRET! equ 1 (
    del /q "!GENERATED_SECRET_FILE!" >nul 2>nul
)
endlocal
goto :eof

:error
echo.
echo === Build failed! ===
if !GENERATED_SECRET! equ 1 (
    del /q "!GENERATED_SECRET_FILE!" >nul 2>nul
)
endlocal
exit /b 1
