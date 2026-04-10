@echo off
cd /d "C:\Users\Lenovo\OneDrive\Desktop\forex_factory_alert"
"C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\python.exe" tools\send_due_emails.py >> .tmp\send_due_output.log 2>&1
