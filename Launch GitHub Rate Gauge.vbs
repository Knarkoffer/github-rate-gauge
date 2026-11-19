Option Explicit

Dim shell, filesystem, scriptPath, errorFile, command, exitCode, errorMessage, errorText
Set shell = CreateObject("WScript.Shell")
Set filesystem = CreateObject("Scripting.FileSystemObject")

' Release the calling WSL terminal while a hidden copy monitors the app.
If WScript.Arguments.Count = 0 Then
    command = Chr(34) & WScript.FullName & Chr(34) & " " & Chr(34) & WScript.ScriptFullName & Chr(34) & " --monitor"
    shell.Run command, 0, False
    WScript.Quit 0
End If

scriptPath = filesystem.BuildPath(filesystem.GetParentFolderName(WScript.ScriptFullName), "Launch GitHub Rate Gauge.cmd")
errorFile = filesystem.BuildPath(shell.ExpandEnvironmentStrings("%TEMP%"), filesystem.GetTempName())
shell.Environment("PROCESS")("GRG_ERROR_FILE") = errorFile
command = "cmd.exe /d /c " & Chr(34) & Chr(34) & scriptPath & Chr(34) & " --background" & Chr(34)
exitCode = shell.Run(command, 0, True)

If exitCode <> 0 Then
    errorMessage = "GitHub Rate Gauge could not start. Run Launch GitHub Rate Gauge.cmd --diagnose from Command Prompt to see the full error."
    If filesystem.FileExists(errorFile) Then
        Set errorText = filesystem.OpenTextFile(errorFile, 1)
        If Not errorText.AtEndOfStream Then errorMessage = errorText.ReadAll
        errorText.Close
    End If
    MsgBox errorMessage, vbOKOnly + vbExclamation, "GitHub Rate Gauge"
End If
If filesystem.FileExists(errorFile) Then filesystem.DeleteFile errorFile, True
