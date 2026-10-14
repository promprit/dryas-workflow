@echo off
rem Dryas command-line entry (owned core D). `dryas memory ...` runs the memory CLI.
if /I "%~1"=="memory" goto memory
echo usage: dryas memory {import-ruflo^|consolidate^|stats} [options] 1>&2
exit /b 2
:memory
shift
rem Python lookup: %DRYAS_PY%, then py -3, then python3, then python. cmd passes at most 9 arguments (%1..%9) here.
if defined DRYAS_PY goto envpy
where py >nul 2>&1 && goto launcher
where python3 >nul 2>&1 && goto py3
goto plain
:envpy
"%DRYAS_PY%" -X utf8 "%~dp0..\jev\memcli.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:launcher
py -3 -X utf8 "%~dp0..\jev\memcli.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:py3
python3 -X utf8 "%~dp0..\jev\memcli.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:plain
python -X utf8 "%~dp0..\jev\memcli.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
