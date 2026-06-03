Get-ChildItem C:\Users\hq362\Downloads -Filter '*.iso' -Recurse -Depth 2 -ErrorAction SilentlyContinue | ForEach-Object { Write-Output "$($_.FullName) | Size: $($_.Length) bytes" }
