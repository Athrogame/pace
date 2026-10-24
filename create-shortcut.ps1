# Puts a "Pace" shortcut on your Desktop that opens Pace as its own app window.
# Run from the pace folder:  powershell -ExecutionPolicy Bypass -File create-shortcut.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "Pace.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$(Join-Path $here 'launch_pace.py')`""
$shortcut.WorkingDirectory = $here
$shortcut.IconLocation = Join-Path $here "frontend\icons\pace.ico"
$shortcut.Description = "Pace: plan around school, work, and sleep"
$shortcut.Save()
Write-Output "Created $link"
