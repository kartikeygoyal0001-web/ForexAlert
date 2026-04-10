@echo off
cd /d "C:\Users\Lenovo\OneDrive\Desktop\forex_factory_alert"
"C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\python.exe" tools\run_morning_alert.py >> .tmp\scheduler_output.log 2>&1
