@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion
echo === Nini Windows Build ===
echo.

set "DEFAULT_NINI_VERSION="
if not defined NINI_VERSION (
    for /f "tokens=2 delims== " %%I in ('findstr /B /C:"version = " pyproject.toml') do set "DEFAULT_NINI_VERSION=%%~I"
    if not defined DEFAULT_NINI_VERSION set "DEFAULT_NINI_VERSION=0.1.0"
)

set "GENERATED_SECRET_FILE=src\nini\_builtin_key.py"
set "GENERATED_SECRET=0"
set "ENABLE_INTERACTIVE_SECRET=1"
set "ENABLE_INTERACTIVE_VERSION=1"
set "ENABLE_INTERACTIVE_MODEL_BUNDLE=1"
set "ENABLE_INTERACTIVE_MODEL_DOWNLOAD=1"
set "HAS_OFFLINE_MODEL_BUNDLE="
set "PREPARE_OFFLINE_MODELS=0"

if defined CI set "ENABLE_INTERACTIVE_SECRET=0"
if /I "%NINI_BUILD_NO_PROMPT%"=="1" set "ENABLE_INTERACTIVE_SECRET=0"
if defined CI set "ENABLE_INTERACTIVE_VERSION=0"
if /I "%NINI_BUILD_NO_PROMPT%"=="1" set "ENABLE_INTERACTIVE_VERSION=0"
if defined CI set "ENABLE_INTERACTIVE_MODEL_BUNDLE=0"
if /I "%NINI_BUILD_NO_PROMPT%"=="1" set "ENABLE_INTERACTIVE_MODEL_BUNDLE=0"
if defined CI set "ENABLE_INTERACTIVE_MODEL_DOWNLOAD=0"
if /I "%NINI_BUILD_NO_PROMPT%"=="1" set "ENABLE_INTERACTIVE_MODEL_DOWNLOAD=0"
if /I "%NINI_PREPARE_OFFLINE_MODELS%"=="1" set "PREPARE_OFFLINE_MODELS=1"

echo [0.5/4] Checking build version...
if defined NINI_VERSION (
    echo [INFO] Use NINI_VERSION from environment: !NINI_VERSION!
) else (
    if "!ENABLE_INTERACTIVE_VERSION!"=="1" (
        set "ASKED_VERSION=0"
        choice /C YN /N /M "Set package version manually? [Y/N]: "
        if !errorlevel! equ 1 (
            set "ASKED_VERSION=1"
            set /p "NINI_VERSION=Enter package version: "
            if not defined NINI_VERSION (
                echo [SKIP] Empty input, fallback to pyproject.toml version.
            )
        )
    )
    if not defined NINI_VERSION (
        set "NINI_VERSION=!DEFAULT_NINI_VERSION!"
        echo [INFO] Use version from pyproject.toml: !NINI_VERSION!
    )
)

echo(!NINI_VERSION!| findstr /R "^[0-9][0-9.]*[-A-Za-z0-9.]*$" >nul
if !errorlevel! neq 0 (
    echo [WARN] Invalid version format "!NINI_VERSION!", fallback to default version.
    if defined DEFAULT_NINI_VERSION (
        set "NINI_VERSION=!DEFAULT_NINI_VERSION!"
    ) else (
        set "NINI_VERSION=0.1.0"
    )
)
echo [0.5/4] Done. Version: !NINI_VERSION!
echo.

echo [1/4] Installing dependencies...
pip install -e .[packaging,webr,local,local_vector,advanced_retrieval]
if !errorlevel! neq 0 (
    echo [FAIL] pip install failed.
    goto :error
)
echo [1/4] Done.
echo.

echo [1.1/4] Checking trial API key input...
if "!ENABLE_INTERACTIVE_SECRET!"=="1" (
    if not defined NINI_BUILTIN_DASHSCOPE_API_KEY (
        choice /C YN /N /M "Embed builtin DashScope API key into packaged app? [Y/N]: "
        if !errorlevel! equ 1 (
            set /p "NINI_BUILTIN_DASHSCOPE_API_KEY=Enter builtin DashScope API key: "
            if defined NINI_BUILTIN_DASHSCOPE_API_KEY (
                echo(!NINI_BUILTIN_DASHSCOPE_API_KEY!| findstr /C:" " >nul
                if !errorlevel! equ 0 (
                    echo [WARN] Builtin DashScope API key contains spaces. Ignoring interactive input.
                    set "NINI_BUILTIN_DASHSCOPE_API_KEY="
                )
            ) else (
                echo [SKIP] Empty input, skip embedding builtin DashScope API key.
            )
        ) else (
            echo [SKIP] Interactive builtin DashScope API key input skipped.
        )
    ) else (
        echo [INFO] NINI_BUILTIN_DASHSCOPE_API_KEY already set from environment, keep existing value.
    )
    if not defined NINI_TRIAL_API_KEY (
        choice /C YN /N /M "Embed optional DeepSeek trial API key fallback? [Y/N]: "
        if !errorlevel! equ 1 (
            set /p "NINI_TRIAL_API_KEY=Enter optional DeepSeek trial API key: "
            if defined NINI_TRIAL_API_KEY (
                echo(!NINI_TRIAL_API_KEY!| findstr /C:" " >nul
                if !errorlevel! equ 0 (
                    echo [WARN] Trial API key contains spaces. Ignoring interactive input.
                    set "NINI_TRIAL_API_KEY="
                )
            ) else (
                echo [SKIP] Empty input, skip embedding trial API key.
            )
        ) else (
            echo [SKIP] Optional DeepSeek trial API key input skipped.
        )
    ) else (
        echo [INFO] NINI_TRIAL_API_KEY already set from environment, keep existing value.
    )
) else (
    echo [SKIP] Interactive trial API key input disabled by CI or NINI_BUILD_NO_PROMPT=1.
)
echo [1.1/4] Done.
echo.

echo [1.2/4] Preparing packaged secrets...
if defined NINI_BUILTIN_DASHSCOPE_API_KEY (
    set "HAS_PACKAGED_SECRET=1"
)
if defined NINI_TRIAL_API_KEY (
    set "HAS_PACKAGED_SECRET=1"
)
if defined HAS_PACKAGED_SECRET (
    if not defined NINI_BUILTIN_DASHSCOPE_API_KEY if defined NINI_TRIAL_API_KEY (
        echo [WARN] Only NINI_TRIAL_API_KEY is set. Default packaged chat will still prefer builtin DashScope models.
        echo        Without NINI_BUILTIN_DASHSCOPE_API_KEY, packaged app may fall back to DeepSeek trial and hit 401 if that key is invalid.
    )
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
set "KALEIDO_CHROME_CACHE_DIR="

if defined NINI_CHROME_CACHE_DIR (
    if exist "!NINI_CHROME_CACHE_DIR!" (
        set "KALEIDO_CHROME_CACHE_DIR=!NINI_CHROME_CACHE_DIR!"
    ) else (
        echo [WARN] NINI_CHROME_CACHE_DIR points to missing path: !NINI_CHROME_CACHE_DIR!
    )
)

if not defined KALEIDO_CHROME_CACHE_DIR (
    for /f "delims=" %%I in ('python -c "from pathlib import Path; import choreographer.cli._cli_utils as cli; path = Path(cli.default_download_path); print(path if path.exists() and any(path.iterdir()) else '')" 2^>nul') do set "KALEIDO_CHROME_CACHE_DIR=%%I"
)

if defined KALEIDO_CHROME_CACHE_DIR (
    echo [INFO] Reusing cached Chromium: !KALEIDO_CHROME_CACHE_DIR!
    set "KALEIDO_CHROME_OK=1"
)

if !KALEIDO_CHROME_OK! neq 1 (
    where kaleido_get_chrome >nul 2>nul
    if !errorlevel! equ 0 (
        call kaleido_get_chrome
        if !errorlevel! equ 0 (
            set "KALEIDO_CHROME_OK=1"
        )
    )
)

if !KALEIDO_CHROME_OK! neq 1 (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%I"
    if defined PYTHON_EXE (
        for %%I in ("!PYTHON_EXE!") do set "PYTHON_DIR=%%~dpI"
        if exist "!PYTHON_DIR!kaleido_get_chrome.exe" (
            call "!PYTHON_DIR!kaleido_get_chrome.exe"
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
    echo        Try: kaleido_get_chrome
    echo        Or : python -c "from choreographer.cli._cli_utils import get_chrome_sync; print(get_chrome_sync())"
)
echo [1.5/4] Done.
echo.

set "DEFAULT_HF_HOME=%USERPROFILE%\.cache\huggingface"
set "DEFAULT_SENTENCE_TRANSFORMERS_HOME=%USERPROFILE%\.cache\torch\sentence_transformers"

echo [1.6/4] Preparing offline retrieval models...
if "!ENABLE_INTERACTIVE_MODEL_DOWNLOAD!"=="1" (
    if "!PREPARE_OFFLINE_MODELS!"=="0" (
        choice /C YN /N /M "Pre-download offline retrieval models now? [Y/N]: "
        if !errorlevel! equ 1 set "PREPARE_OFFLINE_MODELS=1"
    )
) else (
    echo [SKIP] Interactive offline-model download input disabled by CI or NINI_BUILD_NO_PROMPT=1.
)

if "!PREPARE_OFFLINE_MODELS!"=="1" (
    if not defined NINI_HF_HOME set "NINI_HF_HOME=!DEFAULT_HF_HOME!"
    if not defined NINI_SENTENCE_TRANSFORMERS_HOME set "NINI_SENTENCE_TRANSFORMERS_HOME=!DEFAULT_SENTENCE_TRANSFORMERS_HOME!"
    python scripts\prepare_offline_models.py --hf-home "!NINI_HF_HOME!" --sentence-transformers-home "!NINI_SENTENCE_TRANSFORMERS_HOME!"
    if !errorlevel! neq 0 (
        echo [FAIL] Offline model preparation failed.
        goto :error
    )
    set "HAS_OFFLINE_MODEL_BUNDLE=1"
) else (
    echo [SKIP] Offline retrieval model pre-download skipped.
)
echo [1.6/4] Done.
echo.

echo [1.7/4] Checking offline retrieval model bundles...
if "!ENABLE_INTERACTIVE_MODEL_BUNDLE!"=="1" (
    if not defined NINI_HF_HOME (
        if exist "!DEFAULT_HF_HOME!" (
            choice /C YN /N /M "Bundle Hugging Face cache from !DEFAULT_HF_HOME!? [Y/N]: "
            if !errorlevel! equ 1 set "NINI_HF_HOME=!DEFAULT_HF_HOME!"
        ) else (
            echo [INFO] Default Hugging Face cache not found: !DEFAULT_HF_HOME!
        )
    )
    if not defined NINI_SENTENCE_TRANSFORMERS_HOME (
        if exist "!DEFAULT_SENTENCE_TRANSFORMERS_HOME!" (
            choice /C YN /N /M "Bundle sentence-transformers cache from !DEFAULT_SENTENCE_TRANSFORMERS_HOME!? [Y/N]: "
            if !errorlevel! equ 1 set "NINI_SENTENCE_TRANSFORMERS_HOME=!DEFAULT_SENTENCE_TRANSFORMERS_HOME!"
        ) else (
            echo [INFO] Default sentence-transformers cache not found: !DEFAULT_SENTENCE_TRANSFORMERS_HOME!
        )
    )
) else (
    echo [SKIP] Interactive offline-model bundle input disabled by CI or NINI_BUILD_NO_PROMPT=1.
)

if defined NINI_HF_HOME (
    if exist "!NINI_HF_HOME!" (
        echo [INFO] NINI_HF_HOME=!NINI_HF_HOME!
        set "HAS_OFFLINE_MODEL_BUNDLE=1"
    ) else (
        echo [WARN] NINI_HF_HOME points to missing path, ignoring: !NINI_HF_HOME!
        set "NINI_HF_HOME="
    )
)

if defined NINI_SENTENCE_TRANSFORMERS_HOME (
    if exist "!NINI_SENTENCE_TRANSFORMERS_HOME!" (
        echo [INFO] NINI_SENTENCE_TRANSFORMERS_HOME=!NINI_SENTENCE_TRANSFORMERS_HOME!
        set "HAS_OFFLINE_MODEL_BUNDLE=1"
    ) else (
        echo [WARN] NINI_SENTENCE_TRANSFORMERS_HOME points to missing path, ignoring: !NINI_SENTENCE_TRANSFORMERS_HOME!
        set "NINI_SENTENCE_TRANSFORMERS_HOME="
    )
)

if defined HAS_OFFLINE_MODEL_BUNDLE (
    echo [INFO] Offline retrieval model caches will be bundled into the packaged app.
) else (
    echo [WARN] No offline retrieval model cache configured.
    echo        Semantic intent, local vector retrieval, and reranker may still try to fetch models online.
    echo        Set NINI_HF_HOME and/or NINI_SENTENCE_TRANSFORMERS_HOME to bundle local caches.
)
echo [1.7/4] Done.
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

:: ── 准备 WebView2 Runtime 离线安装包（默认启用，可通过 BUNDLE_WEBVIEW2=0 关闭）───
set "WEBVIEW2_DIR=%~dp0packaging\webview2"
set "WEBVIEW2_EXE=%WEBVIEW2_DIR%\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
if not exist "%WEBVIEW2_DIR%" mkdir "%WEBVIEW2_DIR%"

if not exist "%WEBVIEW2_EXE%" (
    if not "%BUNDLE_WEBVIEW2%"=="0" (
        echo [BUILD] 下载离线 WebView2 Runtime 安装包...
        powershell -Command "Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/?linkid=2124701' -OutFile '%WEBVIEW2_EXE%'"
        if errorlevel 1 (
            echo [WARN] WebView2 离线包下载失败，将回退到在线模式
        ) else (
            echo [BUILD] WebView2 离线包已缓存: %WEBVIEW2_EXE%
        )
    )
)

if exist "%WEBVIEW2_EXE%" (
    set "NSIS_EXTRA_ARGS=/DBUNDLE_WEBVIEW2_PATH=%WEBVIEW2_DIR%"
) else (
    set "NSIS_EXTRA_ARGS="
)

echo [3/4] Running PyInstaller...
python -m PyInstaller nini.spec --noconfirm
if !errorlevel! neq 0 (
    echo [FAIL] PyInstaller failed.
    goto :error
)
echo [3/4] Done.
echo.

:: ── EXE 签名（在 NSIS 打包前）──────────────────────────────────────────────
if not "%SIGNING_CERT_THUMBPRINT%"=="" (
    echo [BUILD] 签名可执行文件...
    signtool sign /sha1 "%SIGNING_CERT_THUMBPRINT%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 /d "Nini" dist\nini.exe dist\nini-cli.exe
    if errorlevel 1 (
        echo [ERROR] EXE 签名失败
        exit /b 1
    )
)
echo.

echo [3.5/4] Packaging offline model bundle...
set "OFFLINE_MODELS_ZIP=dist\Nini-!NINI_VERSION!-OfflineModels.zip"
set "DIST_HF_DIR=dist\nini\runtime\models\huggingface"
set "DIST_ST_DIR=dist\nini\runtime\models\sentence-transformers"
set "DIST_INTERNAL_HF_DIR=dist\nini\_internal\runtime\models\huggingface"
set "DIST_INTERNAL_ST_DIR=dist\nini\_internal\runtime\models\sentence-transformers"
set "INSTALLER_STAGE_DIR=dist\nini-installer"
set "HAS_DIST_OFFLINE_MODELS="

if exist "!DIST_HF_DIR!" set "HAS_DIST_OFFLINE_MODELS=1"
if exist "!DIST_ST_DIR!" set "HAS_DIST_OFFLINE_MODELS=1"
if exist "!DIST_INTERNAL_HF_DIR!" set "HAS_DIST_OFFLINE_MODELS=1"
if exist "!DIST_INTERNAL_ST_DIR!" set "HAS_DIST_OFFLINE_MODELS=1"

if defined HAS_DIST_OFFLINE_MODELS (
    if exist "!OFFLINE_MODELS_ZIP!" del /q "!OFFLINE_MODELS_ZIP!" >nul 2>nul
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ErrorActionPreference='Stop';" ^
        "$zip = Resolve-Path 'dist'; $zip = Join-Path $zip 'Nini-!NINI_VERSION!-OfflineModels.zip';" ^
        "$items = @();" ^
        "if (Test-Path 'dist\nini\runtime\models\huggingface') { $items += (Resolve-Path 'dist\nini\runtime\models\huggingface').Path };" ^
        "if (Test-Path 'dist\nini\runtime\models\sentence-transformers') { $items += (Resolve-Path 'dist\nini\runtime\models\sentence-transformers').Path };" ^
        "if (Test-Path 'dist\nini\_internal\runtime\models\huggingface') { $items += (Resolve-Path 'dist\nini\_internal\runtime\models\huggingface').Path };" ^
        "if (Test-Path 'dist\nini\_internal\runtime\models\sentence-transformers') { $items += (Resolve-Path 'dist\nini\_internal\runtime\models\sentence-transformers').Path };" ^
        "if ($items.Count -eq 0) { exit 0 };" ^
        "Compress-Archive -Path $items -DestinationPath $zip -Force"
    if !errorlevel! neq 0 (
        echo [WARN] Offline model archive creation failed. Portable build still keeps bundled models.
    ) else (
        echo [INFO] Offline model archive created: !OFFLINE_MODELS_ZIP!
        echo [INFO] NSIS installer will exclude offline model caches to avoid oversized setup packages.
    )
) else (
    echo [SKIP] No offline model directory found in dist\nini\runtime\models.
)
echo [3.5/4] Done.
echo.

echo [3.6/4] Preparing installer staging directory...
if exist "!INSTALLER_STAGE_DIR!" rmdir /s /q "!INSTALLER_STAGE_DIR!" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$source = Resolve-Path 'dist\nini';" ^
    "$target = Join-Path (Resolve-Path 'dist') 'nini-installer';" ^
    "Copy-Item -Path $source -Destination $target -Recurse -Force;" ^
    "$excluded = @(" ^
    "  (Join-Path $target 'runtime\models\huggingface')," ^
    "  (Join-Path $target 'runtime\models\sentence-transformers')," ^
    "  (Join-Path $target '_internal\runtime\models\huggingface')," ^
    "  (Join-Path $target '_internal\runtime\models\sentence-transformers')" ^
    ");" ^
    "foreach ($path in $excluded) { if (Test-Path $path) { Remove-Item -Path $path -Recurse -Force } }"
if !errorlevel! neq 0 (
    echo [FAIL] Installer staging directory preparation failed.
    goto :error
)
echo [3.6/4] Done.
echo.

echo [4/4] Creating installer...
where makensis >nul 2>nul
if !errorlevel! equ 0 (
    makensis /INPUTCHARSET UTF8 /DPRODUCT_VERSION=!NINI_VERSION! /DPRODUCT_SOURCE_DIR=..\dist\nini-installer %NSIS_EXTRA_ARGS% packaging\installer.nsi
    if !errorlevel! neq 0 (
        echo [WARN] makensis failed, but portable build is still available.
    )
) else (
    echo [SKIP] NSIS not found, skipping installer creation.
    echo        Install from https://nsis.sourceforge.io/ to create setup exe.
)

:: ── 安装包签名（在 NSIS 打包后）────────────────────────────────────────────
if not "%SIGNING_CERT_THUMBPRINT%"=="" (
    echo [BUILD] 签名安装包...
    for %%f in (dist\Nini-*-Setup.exe) do (
        signtool sign /sha1 "%SIGNING_CERT_THUMBPRINT%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 /d "Nini 安装程序" "%%f"
        if errorlevel 1 (
            echo [ERROR] 安装包签名失败
            exit /b 1
        )
    )
    echo [BUILD] 代码签名完成
) else (
    echo [BUILD] 未设置 SIGNING_CERT_THUMBPRINT，跳过代码签名
)
echo.

echo === Build complete! ===
echo GUI Launcher: dist\nini\nini.exe
echo CLI Entry : dist\nini\nini-cli.exe
if exist "dist\Nini-!NINI_VERSION!-Setup.exe" (
    echo Installer : dist\Nini-!NINI_VERSION!-Setup.exe
) else (
    echo Installer : not generated
)
if exist "!OFFLINE_MODELS_ZIP!" (
    echo Offline Models : !OFFLINE_MODELS_ZIP!
)
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
