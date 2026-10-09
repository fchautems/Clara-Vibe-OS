@echo off
call "%~dp0start-clara.cmd" --self-test %*
exit /b %errorlevel%
