Set shell = CreateObject("WScript.Shell")
projectRoot = "C:\BookNest"
pythonwPath = projectRoot & "\venv\Scripts\pythonw.exe"
appPath = projectRoot & "\main_app.py"

shell.CurrentDirectory = projectRoot
shell.Run Chr(34) & pythonwPath & Chr(34) & " " & Chr(34) & appPath & Chr(34), 0, False