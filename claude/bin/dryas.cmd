@echo off
rem Dryas command-line entry (owned core D). `dryas memory ...` runs the memory CLI.
if /I "%~1"=="memory" goto memory
if /I "%~1"=="cloud" goto cloud
echo usage: dryas memory {import-ruflo^|consolidate^|stats} [options] ^| dryas cloud {init^|check^|update^|remove} [options] 1>&2
exit /b 2
:memory
rem shift /1 keeps %0, so %~dp0 still names this bin folder (plain shift moves %0 too).
shift /1
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
exit /b %ERRORLEVEL%
:cloud
if not exist "%~dp0..\..\tools\dryas_cloud.py" (
  echo dryas cloud: needs a Dryas checkout ^(tools\dryas_cloud.py beside claude\^) 1>&2
  exit /b 2
)
if defined DRYAS_PY goto cloudenv
where py >nul 2>&1 && goto cloudpy
where python3 >nul 2>&1 && goto cloudpy3
python -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:cloudenv
"%DRYAS_PY%" -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:cloudpy
py -3 -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
:cloudpy3
python3 -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
