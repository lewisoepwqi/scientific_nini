; Nini Windows 安装脚本 (NSIS)
;
; 使用方式：
;   1. 先执行 pyinstaller nini.spec 生成 dist/nini/ 目录
;   2. 安装 NSIS (https://nsis.sourceforge.io/)
;   3. 执行 makensis packaging/installer.nsi
;   生成文件：dist/Nini-Setup.exe
;
; 前提：dist/nini/ 目录已由 PyInstaller 生成

!include "MUI2.nsh"

; ---- 基本信息 ----
!define PRODUCT_NAME "Nini"
!define PRODUCT_VERSION "0.1.0"
!define PRODUCT_PUBLISHER "Nini Project"
!define PRODUCT_DESCRIPTION "科研数据分析 AI Agent"
!define PRODUCT_EXE "nini.exe"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "..\dist\Nini-${PRODUCT_VERSION}-Setup.exe"
InstallDir "$LOCALAPPDATA\${PRODUCT_NAME}"
InstallDirRegKey HKCU "Software\${PRODUCT_NAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; ---- 界面设置 ----
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${PRODUCT_NAME}"
!define MUI_WELCOMEPAGE_TEXT "Nini 是一个本地优先的科研数据分析 AI Agent。$\r$\n$\r$\n安装程序将引导您完成安装过程。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_PARAMETERS "start"
!define MUI_FINISHPAGE_RUN_TEXT "启动 Nini 服务"

; 如果有图标文件则使用
!if /FileExists "nini.ico"
    !define MUI_ICON "nini.ico"
    !define MUI_UNICON "nini.ico"
!endif

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

; ---- 安装部分 ----
Section "主程序" SecMain
    SectionIn RO  ; 必选

    SetOutPath "$INSTDIR"

    ; 复制 PyInstaller 输出的全部文件
    File /r "..\dist\nini\*.*"

    ; 创建用户数据目录
    CreateDirectory "$PROFILE\.nini"

    ; 写入注册表
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "Version" "${PRODUCT_VERSION}"

    ; 卸载信息（控制面板 > 程序和功能）
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "DisplayName" "${PRODUCT_NAME} - ${PRODUCT_DESCRIPTION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "UninstallString" '"$INSTDIR\uninstall.exe"'
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

Section "开始菜单快捷方式" SecStartMenu
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" \
        "$INSTDIR\${PRODUCT_EXE}" "start" "$INSTDIR\${PRODUCT_EXE}" 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 ${PRODUCT_NAME}.lnk" \
        "$INSTDIR\uninstall.exe"
SectionEnd

Section "桌面快捷方式" SecDesktop
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" \
        "$INSTDIR\${PRODUCT_EXE}" "start" "$INSTDIR\${PRODUCT_EXE}" 0
SectionEnd

; ---- 卸载部分 ----
Section "Uninstall"
    ; 删除程序文件
    RMDir /r "$INSTDIR"

    ; 删除快捷方式
    RMDir /r "$SMPROGRAMS\${PRODUCT_NAME}"
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

    ; 清理注册表
    DeleteRegKey HKCU "Software\${PRODUCT_NAME}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

    ; 提示：不删除用户数据目录 ~/.nini，用户可手动清理
    MessageBox MB_YESNO "是否同时删除用户数据目录（$PROFILE\.nini）？$\r$\n$\r$\n此目录包含您的会话数据、配置和分析结果。" IDNO skip_data
        RMDir /r "$PROFILE\.nini"
    skip_data:
SectionEnd

; ---- 组件描述 ----
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "安装 Nini 核心程序（必选）"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} "在开始菜单创建快捷方式"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "在桌面创建快捷方式"
!insertmacro MUI_FUNCTION_DESCRIPTION_END
