@echo off
rem Dryas command-line entry (owned core D). `dryas memory ...` runs the memory CLI.
if /I "%~1"=="memory" goto memory
echo usage: dryas memory {import-ruflo^|consolidate^|stats} [options] 1>&2
exit /b 2
:memory
shift
set "PYX=%DRYAS_PY%"
if "%PYX%"=="" set "PYX=python"
"%PYX%" -X utf8 "%~dp0..\jev\memcli.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
