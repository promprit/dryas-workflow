@echo off
setlocal
rem Dryas command-line entry (owned core D). `dryas memory ...` runs the memory CLI; `dryas cloud ...` the cloud CLI.
set "DRYAS_SUB="
if /I "%~1"=="memory" set "DRYAS_SUB=memory"
if /I "%~1"=="cloud" set "DRYAS_SUB=cloud"
if defined DRYAS_SUB goto dispatch
echo usage: dryas memory {import-ruflo^|consolidate^|stats} [options] ^| dryas cloud {init^|check^|update^|remove} [options] 1>&2
exit /b 2
:dispatch
if "%DRYAS_SUB%"=="cloud" goto cloud
rem The whole original line goes to Python with %*, quotes and empty arguments intact; the entries drop the leading memory/cloud word.
rem Python lookup: %DRYAS_PY%, then py -3, then python3, then python.
if defined DRYAS_PY goto envpy
where py >nul 2>&1 && goto launcher
where python3 >nul 2>&1 && goto py3
goto plain
:envpy
"%DRYAS_PY%" -X utf8 "%~dp0..\jev\memcli.py" %*
exit /b %ERRORLEVEL%
:launcher
py -3 -X utf8 "%~dp0..\jev\memcli.py" %*
exit /b %ERRORLEVEL%
:py3
python3 -X utf8 "%~dp0..\jev\memcli.py" %*
exit /b %ERRORLEVEL%
:plain
python -X utf8 "%~dp0..\jev\memcli.py" %*
exit /b %ERRORLEVEL%
:cloud
if not exist "%~dp0..\..\tools\dryas_cloud.py" (
  echo dryas cloud: needs a Dryas checkout ^(tools\dryas_cloud.py beside claude\^) 1>&2
  exit /b 2
)
if defined DRYAS_PY goto cloudenv
where py >nul 2>&1 && goto cloudpy
where python3 >nul 2>&1 && goto cloudpy3
python -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %*
exit /b %ERRORLEVEL%
:cloudenv
"%DRYAS_PY%" -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %*
exit /b %ERRORLEVEL%
:cloudpy
py -3 -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %*
exit /b %ERRORLEVEL%
:cloudpy3
python3 -X utf8 "%~dp0..\..\tools\dryas_cloud.py" %*
exit /b %ERRORLEVEL%
