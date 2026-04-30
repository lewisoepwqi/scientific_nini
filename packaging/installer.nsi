; 离线 WebView2 捆绑包路径（可选）：构建时由 /DBUNDLE_WEBVIEW2_PATH=<path> 传入
; 若未定义则回退到在线下载模式
!ifndef BUNDLE_WEBVIEW2_PATH
  !define BUNDLE_WEBVIEW2_PATH ""
!endif

Unicode true

; Nini Windows 安装脚本 (NSIS)
;
; 使用方式（需 NSIS 3.x）：
;   1. 先执行 pyinstaller nini.spec 生成 dist/nini/ 目录
;   2. 安装 NSIS (https://nsis.sourceforge.io/)
;   3. 执行 makensis /INPUTCHARSET UTF8 packaging/installer.nsi
;   生成文件：dist/Nini-Setup.exe
;
; 前提：dist/nini/ 目录已由 PyInstaller 生成

!include "MUI2.nsh"

; ---- 静默安装支持 ----
; NSIS 内置支持以下命令行参数：
;   /S            - 静默模式，无任何交互式对话框
;   /D=<path>     - 自定义安装路径（必须与 /S 结合使用时放在末尾）
; 示例：nini-setup.exe /S /D=C:\Enterprise\Nini
; 详见文档：packaging/README.md - 静默安装

; ---- 基本信息 ----
!define PRODUCT_NAME "Nini"
!ifndef PRODUCT_VERSION
!define PRODUCT_VERSION "0.1.0"
!endif
!define PRODUCT_PUBLISHER "Nini Project"
!define PRODUCT_DESCRIPTION "科研数据分析 AI Agent"
!define PRODUCT_EXE "nini.exe"
!define PRODUCT_CLI_EXE "nini-cli.exe"
!define PRODUCT_ICON "nini.ico"
!define WEBVIEW2_BOOTSTRAPPER_URL "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
!define WEBVIEW2_BOOTSTRAPPER_EXE "$TEMP\MicrosoftEdgeWebView2Setup.exe"
!ifndef PRODUCT_SOURCE_DIR
!define PRODUCT_SOURCE_DIR "..\dist\nini-installer"
!endif

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "..\dist\Nini-${PRODUCT_VERSION}-Setup.exe"
InstallDir "$LOCALAPPDATA\${PRODUCT_NAME}"
InstallDirRegKey HKCU "Software\${PRODUCT_NAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; ---- 界面设置 ----
!define MUI_ABORTWARNING
!define MUI_ICON "nini.ico"
!define MUI_UNICON "nini.ico"
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${PRODUCT_NAME}"
!define MUI_WELCOMEPAGE_TEXT "Nini 是一个本地优先的科研数据分析 AI Agent。$\r$\n$\r$\n安装程序将引导您完成安装过程。"
!define MUI_FINISHPAGE_NOAUTOCLOSE
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "启动 Nini"

; ---- 安装页面 ----
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; ---- 卸载页面 ----
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ---- 语言 ----
!insertmacro MUI_LANGUAGE "SimpChinese"

; ---- WebView2 Runtime 检测与补齐 ----
Function HasWebView2Runtime
    StrCpy $0 "0"
    IfFileExists "$PROGRAMFILES32\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe" found
    IfFileExists "$PROGRAMFILES64\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe" found
    IfFileExists "$LOCALAPPDATA\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe" found
    Return
found:
    StrCpy $0 "1"
FunctionEnd

Function EnsureWebView2Runtime
  Call HasWebView2Runtime
  Pop $0
  ${If} $0 == "yes"
    Return
  ${EndIf}

  ; 离线模式：使用捆绑的安装包
  !if "${BUNDLE_WEBVIEW2_PATH}" != ""
    DetailPrint "正在安装离线 WebView2 Runtime..."
    ExecWait '"$INSTDIR\webview2\MicrosoftEdgeWebView2RuntimeInstallerX64.exe" /silent /install' $0
    ${If} $0 != 0
      IfSilent +2
        MessageBox MB_OK|MB_ICONEXCLAMATION "WebView2 Runtime 离线安装失败（错误码：$0）。$\n请联系管理员或手动安装。"
      SetErrorLevel 1
      Abort
    ${EndIf}
    Return
  !endif

  ; 在线模式：下载 Bootstrapper（现有逻辑）
  DetailPrint "正在下载 WebView2 Runtime 安装程序..."
  NSISdl::download \
    "https://go.microsoft.com/fwlink/p/?LinkId=2124703" \
    "$TEMP\MicrosoftEdgeWebView2Setup.exe"
  Pop $0
  ${If} $0 != "success"
    IfSilent +2
      MessageBox MB_OK|MB_ICONEXCLAMATION "WebView2 Runtime 下载失败。$\n请检查网络连接后重试，或联系管理员手动安装。"
    SetErrorLevel 1
    Abort
  ${EndIf}
  ExecWait '"$TEMP\MicrosoftEdgeWebView2Setup.exe" /silent /install' $0
  Delete "$TEMP\MicrosoftEdgeWebView2Setup.exe"
  ${If} $0 != 0
    IfSilent +2
      MessageBox MB_OK|MB_ICONEXCLAMATION "WebView2 Runtime 安装失败（错误码：$0）。$\n请联系管理员或手动安装。"
    SetErrorLevel 1
    Abort
  ${EndIf}
FunctionEnd

; ---- 安装部分 ----
Section "主程序" SecMain
    SectionIn RO  ; 必选

    SetOutPath "$INSTDIR"

  ; 如果有捆绑 WebView2，拷贝到安装目录
  !if "${BUNDLE_WEBVIEW2_PATH}" != ""
    SetOutPath "$INSTDIR\webview2"
    File "${BUNDLE_WEBVIEW2_PATH}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    SetOutPath "$INSTDIR"
  !endif

    Call EnsureWebView2Runtime

    ; 复制安装器专用瘦身目录（由 build_windows.bat 预先生成）
    File /r "${PRODUCT_SOURCE_DIR}\*.*"

    ; 复制图标文件到安装目录（供快捷方式使用）
    File "nini.ico"

    ; 创建用户数据目录
    CreateDirectory "$PROFILE\.nini"

    ; 创建桌面快捷方式（默认包含）
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" \
        "$INSTDIR\${PRODUCT_EXE}" "" \
        "$INSTDIR\${PRODUCT_ICON}" 0

    ; 创建开始菜单快捷方式
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" \
        "$INSTDIR\${PRODUCT_EXE}" "" \
        "$INSTDIR\${PRODUCT_ICON}" 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\命令行工具.lnk" \
        "$INSTDIR\${PRODUCT_CLI_EXE}" "" \
        "$INSTDIR\${PRODUCT_ICON}" 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 ${PRODUCT_NAME}.lnk" \
        "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0

    ; 写入注册表
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "Version" "${PRODUCT_VERSION}"

    ; 卸载信息（控制面板 > 程序和功能）
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "DisplayName" "${PRODUCT_NAME} - ${PRODUCT_DESCRIPTION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "DisplayIcon" '"$INSTDIR\${PRODUCT_ICON}"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "NoRepair" 1

    ; 生成卸载程序
    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

; ---- 卸载部分 ----
Section "Uninstall"
    ; 删除程序文件
    RMDir /r "$INSTDIR"

    ; 删除快捷方式
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
    RMDir /r "$SMPROGRAMS\${PRODUCT_NAME}"

    ; 清理注册表
    DeleteRegKey HKCU "Software\${PRODUCT_NAME}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

    ; 提示：是否删除用户数据
    ; 静默模式下默认不删除用户数据（保护用户数据安全）
    IfSilent skip_data
      MessageBox MB_YESNO "是否同时删除用户数据目录（$PROFILE\.nini）？$\r$\n$\r$\n此目录包含您的会话数据、配置和分析结果。" IDNO skip_data
        RMDir /r "$PROFILE\.nini"
    skip_data:
SectionEnd
