$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Code = Join-Path $Root ".runtime\tools\vscode\bin\code.cmd"
$ExtensionsDir = Join-Path $Root ".runtime\tools\vscode-extensions"
$UserDataDir = Join-Path $Root ".runtime\tools\vscode-user-data"
$Workspace = Join-Path $Root "mini-ogas.code-workspace"

if (-not (Test-Path $Code)) {
    throw "VS Code portable is not installed. Run .\scripts\setup-editor.ps1 or ask Codex to reinstall it."
}

& $Code --extensions-dir $ExtensionsDir --user-data-dir $UserDataDir $Workspace
