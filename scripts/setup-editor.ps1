$ErrorActionPreference = "Stop"
. "$PSScriptRoot\env.ps1"

$codeDir = Join-Path $script:ToolsDir "vscode"
$codeExe = Join-Path $codeDir "Code.exe"
$codeCmd = Join-Path $codeDir "bin\code.cmd"
$zip = Join-Path $script:ToolsDir "vscode-win32-x64-archive-stable.zip"
$extensionsDir = Join-Path $script:ToolsDir "vscode-extensions"
$userDataDir = Join-Path $script:ToolsDir "vscode-user-data"

if (-not (Test-Path $codeExe)) {
    $url = "https://update.code.visualstudio.com/latest/win32-x64-archive/stable"
    $extract = Join-Path $script:ToolsDir "vscode-extract"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    if (Test-Path $extract) {
        Remove-Item -LiteralPath $extract -Recurse -Force
    }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $foundCode = Get-ChildItem -Path $extract -Recurse -Filter Code.exe | Select-Object -First 1
    if (-not $foundCode) {
        throw "Code.exe not found after extraction."
    }
    $parent = Split-Path -Parent $foundCode.FullName
    if (Test-Path $codeDir) {
        Remove-Item -LiteralPath $codeDir -Recurse -Force
    }
    Move-Item -LiteralPath $parent -Destination $codeDir
    if (Test-Path $extract) {
        Remove-Item -LiteralPath $extract -Recurse -Force
    }
}

New-Item -ItemType Directory -Force -Path $extensionsDir, $userDataDir | Out-Null

$extensions = @(
    "ms-python.python",
    "ms-python.vscode-pylance",
    "Vue.volar",
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "golang.go",
    "ms-vscode.powershell",
    "redhat.vscode-yaml",
    "eamodio.gitlens"
)

foreach ($extension in $extensions) {
    & $codeCmd --extensions-dir $extensionsDir --user-data-dir $userDataDir --install-extension $extension --force
}

& $codeCmd --extensions-dir $extensionsDir --user-data-dir $userDataDir --version
