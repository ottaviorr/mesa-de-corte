' Mesa de Corte.vbs - abre o app SEM terminal (duplo clique ou atalho).
' Sobe o backend escondido (iniciar_app.sh --sem-terminal) e abre o navegador.
' Se ja estiver no ar, so abre o navegador. Log em trabalho\app.log.
' Pra fechar o app: "Fechar Mesa de Corte.vbs".
Option Explicit
Dim sh, fso, raiz, url, bash, i
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
raiz = fso.GetParentFolderName(WScript.ScriptFullName)
url = "http://localhost:8765/"

Function NoAr()
  Dim http
  On Error Resume Next
  Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
  http.setTimeouts 500, 500, 1000, 1000
  http.Open "GET", url & "api/status", False
  http.Send
  NoAr = (Err.Number = 0 And http.Status = 200)
End Function

If Not NoAr() Then
  bash = sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Git\bin\bash.exe"
  If Not fso.FileExists(bash) Then
    MsgBox "Nao achei o Git Bash em:" & vbCrLf & bash & vbCrLf & vbCrLf & _
           "Instale o Git for Windows e tente de novo.", vbExclamation, "Mesa de Corte"
    WScript.Quit 1
  End If
  ' CHERE_INVOKING: o bash de login nao pula pra pasta HOME
  sh.Environment("PROCESS")("CHERE_INVOKING") = "1"
  sh.CurrentDirectory = raiz
  sh.Run """" & bash & """ -lc ""./iniciar_app.sh --sem-terminal > trabalho/app.log 2>&1""", 0, False
  For i = 1 To 60                          ' espera ate ~30s o servidor subir
    WScript.Sleep 500
    If NoAr() Then Exit For
  Next
  If Not NoAr() Then
    MsgBox "O app nao subiu. Veja o log em:" & vbCrLf & raiz & "\trabalho\app.log", _
           vbExclamation, "Mesa de Corte"
    WScript.Quit 1
  End If
End If

sh.Run url
