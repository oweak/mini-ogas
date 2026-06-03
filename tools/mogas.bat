@echo off
:: mogas.bat — Windows shortcut for Mini-OGAS System Manager
:: Usage: mogas up / mogas down / mogas status / ...
setlocal
cd /d "%~dp0.."
python -m tools.mogas %*
