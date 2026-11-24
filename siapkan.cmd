@echo off
rem Penyiapan kit agent. Klik dua kali berkas ini di folder hasil clone, lalu jawab pertanyaannya.
rem Boleh dijalankan lagi kapan saja, misalnya sesudah git pull: jawaban terakhir ditawarkan lagi.
rem Opsi pasang.py boleh ditulis di belakangnya, misalnya: siapkan.cmd --tanpa-rag
rem
rem Berkas ini hanya mencari Python. Pertanyaan dan pemasangannya ada di pasang.py.
rem Sengaja tanpa goto dan label, karena cmd bisa salah membaca label di berkas berakhiran baris LF.
setlocal
title Penyiapan kit agent
cd /d "%~dp0"
if not exist "%~dp0pasang.py" (
    echo pasang.py tidak ada di folder ini. Jalankan siapkan.cmd dari folder hasil clone repo kit.
    pause
    exit /b 1
)
rem Python dari Microsoft Store dilewati: path-nya berganti setiap kali diperbarui, padahal hook menyimpan path itu.
set "CEK=import sys; sys.exit(sys.version_info < (3, 10) or 'WindowsApps' in sys.base_prefix)"
set "PY="
echo Mencari Python 3.10 atau lebih baru...
rem call, karena python bisa berupa berkas .bat (misalnya pyenv-win), yang tanpa call tidak pernah kembali ke sini.
call py -3 -c "%CEK%" >nul 2>nul && set "PY=py -3"
if not defined PY call python -c "%CEK%" >nul 2>nul && set "PY=python"
if not defined PY (
    echo Butuh Python 3.10 atau lebih baru dari python.org, dan belum ditemukan di komputer ini.
    where winget >nul 2>nul
    if not errorlevel 1 (
        choice /c YT /n /m "Pasang Python 3.14 sekarang lewat winget? [Y/T] "
        if not errorlevel 2 if errorlevel 1 call winget install --id Python.Python.3.14 --exact --source winget
    )
    echo.
    echo Sesudah Python terpasang, tutup jendela ini lalu jalankan siapkan.cmd lagi.
    echo Unduhan manualnya di https://www.python.org/downloads/
    pause
    exit /b 1
)
call %PY% "%~dp0pasang.py" --tanya %*
set "KODE=%ERRORLEVEL%"
echo.
pause
exit /b %KODE%
