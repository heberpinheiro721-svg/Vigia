Dim fso, WShell, pasta
Set fso    = CreateObject("Scripting.FileSystemObject")
Set WShell = CreateObject("WScript.Shell")

pasta = fso.GetParentFolderName(WScript.ScriptFullName)

WShell.Run "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & pasta & "\iniciar.ps1""", 0, False
