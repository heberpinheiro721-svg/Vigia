$vigia = "C:\Users\heber\OneDrive\Projetos IA\VIGIA"

# Encerra instâncias anteriores
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Inicia Streamlit redirecionando output para log (resolve problema de console ausente)
Start-Process -FilePath "$vigia\venv\Scripts\streamlit.exe" `
    -ArgumentList "run", "app.py", "--server.port", "8501" `
    -WorkingDirectory $vigia `
    -NoNewWindow `
    -RedirectStandardOutput "$vigia\streamlit.log" `
    -RedirectStandardError "$vigia\streamlit_err.log"

Start-Sleep -Seconds 8
Start-Process "http://localhost:8501"
