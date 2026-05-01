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

:: ── 设置版本隔离输出目录 ──────────────────────────────────────────────────
set "VERSION_DIST_DIR=dist\v!NINI_VERSION!"
set "VERSION_BUILD_DIR=build\v!NINI_VERSION!"

:: ── 清理旧版本打包目录（默认保留，设置 NINI_CLEAN_OLD_VERSIONS=1 时清理）──
echo [0.6/4] Checking old versioned build directories...
if /I "!NINI_CLEAN_OLD_VERSIONS!"=="1" (
    echo [CLEAN] NINI_CLEAN_OLD_VERSIONS=1, cleaning old versions...
    if exist "dist\v*" (
        for /d %%D in ("dist\v*") do (
            if /I not "%%~nxD"=="v!NINI_VERSION!" (
                echo [CLEAN] Removing old version directory: %%D
                rmdir /s /q "%%D" >nul 2>nul
            )
        )
    )
    if exist "build\v*" (
        for /d %%D in ("build\v*") do (
            if /I not "%%~nxD"=="v!NINI_VERSION!" (
                echo [CLEAN] Removing old build directory: %%D
                rmdir /s /q "%%D" >nul 2>nul
            )
        )
    )
    echo [0.6/4] Old versions cleaned.
) else (
    echo [SKIP] Preserving old version directories. Set NINI_CLEAN_OLD_VERSIONS=1 to clean.
)
echo [0.6/4] Done.
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

echo [2.5/4] Baking version !NINI_VERSION! into Python source files...
python scripts\bake_version.py !NINI_VERSION!
if !errorlevel! neq 0 (
    echo [FAIL] Version baking failed.
    goto :error
)
echo [2.5/4] Done.
echo.

echo [3/4] Running PyInstaller...
python -m PyInstaller nini.spec --noconfirm --distpath "!VERSION_DIST_DIR!" --workpath "!VERSION_BUILD_DIR!"
if !errorlevel! neq 0 (
    echo [FAIL] PyInstaller failed.
    goto :error
)
echo [3/4] Done.
echo.

:: ── EXE 签名（在 NSIS 打包前）──────────────────────────────────────────────
if not "%SIGNING_CERT_THUMBPRINT%"=="" (
    echo [BUILD] 签名可执行文件...
    signtool sign /sha1 "%SIGNING_CERT_THUMBPRINT%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 /d "Nini" "!VERSION_DIST_DIR!\nini\nini.exe" "!VERSION_DIST_DIR!\nini\nini-cli.exe" "!VERSION_DIST_DIR!\nini\nini-updater.exe"
    if errorlevel 1 (
        echo [ERROR] EXE 签名失败
        exit /b 1
    )
)
echo.

echo [3.5/4] Packaging offline model bundle...
set "OFFLINE_MODELS_ZIP=!VERSION_DIST_DIR!\Nini-!NINI_VERSION!-OfflineModels.zip"
set "DIST_HF_DIR=!VERSION_DIST_DIR!\nini\runtime\models\huggingface"
set "DIST_ST_DIR=!VERSION_DIST_DIR!\nini\runtime\models\sentence-transformers"
set "DIST_INTERNAL_HF_DIR=!VERSION_DIST_DIR!\nini\_internal\runtime\models\huggingface"
set "DIST_INTERNAL_ST_DIR=!VERSION_DIST_DIR!\nini\_internal\runtime\models\sentence-transformers"
set "INSTALLER_STAGE_DIR=!VERSION_DIST_DIR!\nini-installer"
set "HAS_DIST_OFFLINE_MODELS="

if exist "!DIST_HF_DIR!" set "HAS_DIST_OFFLINE_MODELS=1"
if exist "!DIST_ST_DIR!" set "HAS_DIST_OFFLINE_MODELS=1"
if exist "!DIST_INTERNAL_HF_DIR!" set "HAS_DIST_OFFLINE_MODELS=1"
if exist "!DIST_INTERNAL_ST_DIR!" set "HAS_DIST_OFFLINE_MODELS=1"

if defined HAS_DIST_OFFLINE_MODELS (
    if exist "!OFFLINE_MODELS_ZIP!" del /q "!OFFLINE_MODELS_ZIP!" >nul 2>nul
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ErrorActionPreference='Stop';" ^
        "$distDir = Resolve-Path '!VERSION_DIST_DIR!';" ^
        "$zip = Join-Path $distDir 'Nini-!NINI_VERSION!-OfflineModels.zip';" ^
        "$items = @();" ^
        "if (Test-Path '$distDir\nini\runtime\models\huggingface') { $items += (Resolve-Path '$distDir\nini\runtime\models\huggingface').Path };" ^
        "if (Test-Path '$distDir\nini\runtime\models\sentence-transformers') { $items += (Resolve-Path '$distDir\nini\runtime\models\sentence-transformers').Path };" ^
        "if (Test-Path '$distDir\nini\_internal\runtime\models\huggingface') { $items += (Resolve-Path '$distDir\nini\_internal\runtime\models\huggingface').Path };" ^
        "if (Test-Path '$distDir\nini\_internal\runtime\models\sentence-transformers') { $items += (Resolve-Path '$distDir\nini\_internal\runtime\models\sentence-transformers').Path };" ^
        "if ($items.Count -eq 0) { exit 0 };" ^
        "Compress-Archive -Path $items -DestinationPath $zip -Force"
    if !errorlevel! neq 0 (
        echo [WARN] Offline model archive creation failed. Portable build still keeps bundled models.
    ) else (
        echo [INFO] Offline model archive created: !OFFLINE_MODELS_ZIP!
        echo [INFO] NSIS installer will exclude offline model caches to avoid oversized setup packages.
    )
) else (
    echo [SKIP] No offline model directory found in !VERSION_DIST_DIR!\nini\runtime\models.
)
echo [3.5/4] Done.
echo.

echo [3.6/4] Preparing installer staging directory...
if exist "!INSTALLER_STAGE_DIR!" rmdir /s /q "!INSTALLER_STAGE_DIR!" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$distDir = Resolve-Path '!VERSION_DIST_DIR!';" ^
    "$source = Join-Path $distDir 'nini';" ^
    "$target = Join-Path $distDir 'nini-installer';" ^
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
set "INSTALLER_OUTFILE=!VERSION_DIST_DIR!\Nini-!NINI_VERSION!-Setup.exe"
where makensis >nul 2>nul
if !errorlevel! equ 0 (
    makensis /INPUTCHARSET UTF8 /DPRODUCT_VERSION=!NINI_VERSION! /DPRODUCT_SOURCE_DIR=..\!VERSION_DIST_DIR!\nini-installer /DOUTFILE_PATH=..\!VERSION_DIST_DIR!\Nini-!NINI_VERSION!-Setup.exe %NSIS_EXTRA_ARGS% packaging\installer.nsi
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
    for %%f in (!VERSION_DIST_DIR!\Nini-*-Setup.exe) do (
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

set "INSTALLER_PATH=!VERSION_DIST_DIR!\Nini-!NINI_VERSION!-Setup.exe"

if exist "!INSTALLER_PATH!" (
    echo [4.1/4] Generating installer SHA256...
    python -c "import hashlib,os,sys;p=sys.argv[1];h=hashlib.sha256();f=open(p,'rb');[h.update(b) for b in iter(lambda:f.read(1048576),b'')];f.close();open(p+'.sha256','w',encoding='ascii').write(h.hexdigest()+'  '+os.path.basename(p)+'\n')" "!INSTALLER_PATH!"
    if !errorlevel! neq 0 (
        echo [FAIL] SHA256 generation failed.
        goto :error
    )

    :: ── 读取发布配置（优先使用 config/release.conf）──────────────────────────
    set "RELEASE_CONF=config\release.conf"
    set "UPDATE_ASSET_BASE_URL="
    set "UPDATE_CHANNEL="
    set "UPDATE_NOTES="
    set "UPDATE_ALLOW_INSECURE_HTTP="

    if exist "!RELEASE_CONF!" (
        echo [4.2/4] Reading release configuration from !RELEASE_CONF!...
        for /f "tokens=1,2 delims== " %%a in ('findstr /R "^url \= ^channel \= ^allow_insecure_http \= ^default_notes \= " !RELEASE_CONF!') do (
            if "%%a"=="url" set "UPDATE_ASSET_BASE_URL=%%b"
            if "%%a"=="channel" set "UPDATE_CHANNEL=%%b"
            if "%%a"=="allow_insecure_http" set "UPDATE_ALLOW_INSECURE_HTTP=%%b"
            if "%%a"=="default_notes" set "UPDATE_NOTES=%%b"
        )
        :: 去掉可能存在的引号
        set "UPDATE_ASSET_BASE_URL=!UPDATE_ASSET_BASE_URL:"=!"
        set "UPDATE_CHANNEL=!UPDATE_CHANNEL:"=!"
        set "UPDATE_ALLOW_INSECURE_HTTP=!UPDATE_ALLOW_INSECURE_HTTP:"=!"
        set "UPDATE_NOTES=!UPDATE_NOTES:"=!"
    )

    :: 环境变量优先级高于配置文件
    if defined NINI_UPDATE_ASSET_BASE_URL set "UPDATE_ASSET_BASE_URL=!NINI_UPDATE_ASSET_BASE_URL!"
    if not defined UPDATE_ASSET_BASE_URL if defined NINI_UPDATE_BASE_URL set "UPDATE_ASSET_BASE_URL=!NINI_UPDATE_BASE_URL!"
    if defined NINI_UPDATE_CHANNEL set "UPDATE_CHANNEL=!NINI_UPDATE_CHANNEL!"
    if defined NINI_UPDATE_NOTES set "UPDATE_NOTES=!NINI_UPDATE_NOTES!"
    if not defined NINI_UPDATE_CHANNEL if not defined UPDATE_CHANNEL set "UPDATE_CHANNEL=stable"
    if not defined NINI_UPDATE_NOTES if not defined UPDATE_NOTES set "UPDATE_NOTES=Nini !NINI_VERSION! 发布"

    if defined UPDATE_ASSET_BASE_URL (
        set "MANIFEST_HTTP_ARG="
        if /I "!UPDATE_ALLOW_INSECURE_HTTP!"=="true" set "MANIFEST_HTTP_ARG=--allow-insecure-http"
        if /I "!UPDATE_ALLOW_INSECURE_HTTP!"=="1" set "MANIFEST_HTTP_ARG=--allow-insecure-http"
        if /I "!NINI_UPDATE_ALLOW_INSECURE_HTTP!"=="1" set "MANIFEST_HTTP_ARG=--allow-insecure-http"
        if /I "!NINI_UPDATE_ALLOW_INSECURE_HTTP!"=="true" set "MANIFEST_HTTP_ARG=--allow-insecure-http"

        echo [4.2/4] Generating update manifest draft...
        python scripts\generate_update_manifest.py --installer "!INSTALLER_PATH!" --version "!NINI_VERSION!" --channel "!UPDATE_CHANNEL!" --base-url "!UPDATE_ASSET_BASE_URL!" --notes "!UPDATE_NOTES!" !MANIFEST_HTTP_ARG! --output "!VERSION_DIST_DIR!\latest.json"
        if !errorlevel! neq 0 (
            echo [FAIL] update manifest generation failed.
            goto :error
        )
        python scripts\verify_update_manifest.py --manifest "!VERSION_DIST_DIR!\latest.json" --installer "!INSTALLER_PATH!"
        if !errorlevel! neq 0 (
            echo [FAIL] update manifest verification failed.
            goto :error
        )

        echo [4.3/4] Generating upload scripts...
        python scripts\generate_upload_script.py --version "!NINI_VERSION!" --installer-dir "!VERSION_DIST_DIR!" --config "!RELEASE_CONF!" --output-dir "!VERSION_DIST_DIR!"
        if !errorlevel! neq 0 (
            echo [WARN] upload script generation failed.
        )
    ) else (
        echo [SKIP] NINI_UPDATE_ASSET_BASE_URL / config/release.conf not set, skip update manifest draft.
    )
) else (
    echo [SKIP] Installer not generated, skip SHA256 and update manifest.
)


echo.

echo === Build complete! ===
echo Version Output: !VERSION_DIST_DIR!\nini.exe
echo GUI Launcher : !VERSION_DIST_DIR!\nini\nini.exe
echo CLI Entry    : !VERSION_DIST_DIR!\nini\nini-cli.exe
echo Updater      : !VERSION_DIST_DIR!\nini\nini-updater.exe
if exist "!VERSION_DIST_DIR!\Nini-!NINI_VERSION!-Setup.exe" (
    echo Installer    : !VERSION_DIST_DIR!\Nini-!NINI_VERSION!-Setup.exe
    if exist "!VERSION_DIST_DIR!\Nini-!NINI_VERSION!-Setup.exe.sha256" echo SHA256       : !VERSION_DIST_DIR!\Nini-!NINI_VERSION!-Setup.exe.sha256
    if exist "!VERSION_DIST_DIR!\latest.json" echo Manifest     : !VERSION_DIST_DIR!\latest.json
    if exist "!VERSION_DIST_DIR!\upload.bat" echo Upload Script: !VERSION_DIST_DIR!\upload.bat
    if exist "!VERSION_DIST_DIR!\upload.ps1" echo Upload Script: !VERSION_DIST_DIR!\upload.ps1
    if exist "!VERSION_DIST_DIR!\UPLOAD_INSTRUCTIONS.txt" echo Instructions : !VERSION_DIST_DIR!\UPLOAD_INSTRUCTIONS.txt
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
