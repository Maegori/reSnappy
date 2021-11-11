@echo off

setlocal

:loop
if not "%1" == "" (
    if "%1" == "-inv" (
        set "invert=true"
        shift
    )
    if "%1" == "-o" (
        set output=%2
        shift
    ) 
    if "%1" == "-s" (
        set source=%2
        shift
    )
    shift
    goto :loop
)

if defined output (set o=-o %output%) else (set output=temp)
if defined source (set s=-s %source%)
if defined invert (set inv=-inv) 

python pysnap.py %o% %s% %inv%
powershell -command "& {&'Set-Clipboard' -Path %output%.png"}  
