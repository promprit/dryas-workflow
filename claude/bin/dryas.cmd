@echo off
setlocal
rem Dryas command-line entry (owned core D). `dryas memory ...` runs the memory CLI; `dryas cloud ...` the cloud CLI.
set "DRYAS_SUB="
if /I "%~1"=="memory" set "DRYAS_SUB=memory"
if /I "%~1"=="cloud" set "DRYAS_SUB=cloud"
if defined DRYAS_SUB goto args
echo usage: dryas memory {import-ruflo^|consolidate^|stats} [options] ^| dryas cloud {init^|check^|update^|remove} [options] 1>&2
exit /b 2
:args
rem shift /1 keeps %0, so %~dp0 still names this bin folder (plain shift moves %0 too).
shift /1
rem Collect every remaining argument, quotes intact, so there is no cap on how many cmd forwards.
set "DRYAS_ARGS="
:collect
if "%~1"=="" goto dispatch
set "DRYAS_ARGS=%DRYAS_ARGS% %1"
shift /1
goto collect
:dispatch
if "%DRYAS_SUB%"=="cloud" goto cloud
rem Python lookup: %DRYAS_PY%, then py -3, then python3, then python.
if defined DRYAS_PY goto envpy
where py >nul 2>&1 && goto launcher
where python3 >nul 2>&1 && goto py3
goto plain
:envpy
"%DRYAS_PY%" -X utf8 "%~dp0..\jev\memcli.py"%DRYAS_ARGS%
exit /b %ERRORLEVEL%
:launcher
py -3 -X utf8 "%~dp0..\jev\memcli.py"%DRYAS_ARGS%
exit /b %ERRORLEVEL%
:py3
python3 -X utf8 "%~dp0..\jev\memcli.py"%DRYAS_ARGS%
exit /b %ERRORLEVEL%
:plain
python -X utf8 "%~dp0..\jev\memcli.py"%DRYAS_ARGS%
exit /b %ERRORLEVEL%
:cloud
if not exist "%~dp0..\..\tools\dryas_cloud.py" (
  echo dryas cloud: needs a Dryas checkout ^(tools\dryas_cloud.py beside claude\^) 1>&2
  exit /b 2
)
if defined DRYAS_PY goto cloudenv
where py >nul 2>&1 && goto cloudpy
where python3 >nul 2>&1 && goto cloudpy3
python -X utf8 "%~dp0..\..\tools\dryas_cloud.py"%DRYAS_ARGS%
exit /b %ERRORLEVEL%
:cloudenv
"%DRYAS_PY%" -X utf8 "%~dp0..\..\tools\dryas_cloud.py"%DRYAS_ARGS%
exit /b %ERRORLEVEL%
:cloudpy
py -3 -X utf8 "%~dp0..\..\tools\dryas_cloud.py"%DRYAS_ARGS%
exit /b %ERRORLEVEL%
:cloudpy3
python3 -X utf8 "%~dp0..\..\tools\dryas_cloud.py"%DRYAS_ARGS%
exit /b %ERRORLEVEL%
