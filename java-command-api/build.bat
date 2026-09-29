@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if exist out rmdir /s /q out
mkdir out

set "SOURCES="
for /r "src\main\java" %%f in (*.java) do set "SOURCES=!SOURCES! "%%f""
for /r "src\test\java" %%f in (*.java) do set "SOURCES=!SOURCES! "%%f""

echo Compiling Java sources...
javac -d out !SOURCES!
if errorlevel 1 (
    echo Compilation failed.
    exit /b 1
)

set "VECTORS=%~1"
if "%VECTORS%"=="" set "VECTORS=..\hash_vectors.json"

if not exist "%VECTORS%" (
    echo No vectors file at %VECTORS%.
    echo Generate one first: python -m tools.export_hash_vectors hash_vectors.json
    exit /b 1
)

echo Running ParityCheck against %VECTORS%...
java -cp out bagay.chain.ParityCheck "%VECTORS%"
exit /b %errorlevel%
