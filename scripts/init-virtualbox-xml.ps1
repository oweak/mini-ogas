$xmlContent = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VirtualBox xmlns="http://www.virtualbox.org/" version="1.12-windows">
  <Global>
    <ExtraData>
    </ExtraData>
    <MachineRegistry>
    </MachineRegistry>
    <MediaRegistry>
    </MediaRegistry>
    <NetserviceRegistry>
    </NetserviceRegistry>
  </Global>
</VirtualBox>
"@
$path = "$env:USERPROFILE\.VirtualBox\VirtualBox.xml"
try {
    Set-Content -Path $path -Value $xmlContent -Encoding UTF8 -ErrorAction Stop
    Write-Host "OK: VirtualBox.xml created at $path"
} catch {
    Write-Host "FAILED: $_"
}
