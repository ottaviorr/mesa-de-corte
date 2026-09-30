' Fechar Mesa de Corte.vbs - encerra o app aberto pelo "Mesa de Corte.vbs"
' (mata o processo da porta 8765 e os filhos, ex. um ffmpeg no meio da edicao).
' Nao mexe em entrada/ nem saida/.
Option Explicit
Dim sh, r
Set sh = CreateObject("WScript.Shell")
r = MsgBox("Fechar a Mesa de Corte?" & vbCrLf & _
           "Se houver uma edicao rodando, ela sera interrompida.", _
           vbQuestion + vbYesNo, "Mesa de Corte")
If r = vbYes Then
  sh.Run "powershell -NoProfile -WindowStyle Hidden -Command ""Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { taskkill /PID $_.OwningProcess /T /F }""", 0, True
End If
