# Setup Scheduler Workflow

## Objective
Configure Windows Task Scheduler to run the morning alert pipeline automatically
at 06:30 UTC every weekday (Mon–Fri).

## Prerequisites
- Python installed and accessible as `python` in PATH
- Pipeline tested manually with `--dry-run` successfully
- `gmail_credentials.json` and `token.json` present at project root
- `.env` file populated with real API key

## One-Time Setup Steps

### Step 1: Find your Python path
```cmd
where python
```
Copy the full path (e.g., `C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\python.exe`)

### Step 2: Register the scheduled task
Open **Command Prompt as Administrator** and run:

```cmd
schtasks /create ^
  /tn "ForexMorningAlert" ^
  /tr "\"C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\python.exe\" \"C:\Users\Lenovo\OneDrive\Desktop\forex_factory_alert\tools\run_morning_alert.py\"" ^
  /sc daily ^
  /st 06:30 ^
  /ru SYSTEM ^
  /f
```

> **Note on time:** `/st 06:30` is your local system time, NOT UTC.
> If your PC is set to UTC+0, use 06:30. If UTC+5 (Pakistan), use 11:30.
> Adjust accordingly.

### Step 3: Set the working directory
Windows Task Scheduler doesn't set working directory automatically. Use this wrapper approach:

Create a file `run_alert.bat` at the project root:
```bat
@echo off
cd /d "C:\Users\Lenovo\OneDrive\Desktop\forex_factory_alert"
python tools\run_morning_alert.py >> .tmp\scheduler_output.log 2>&1
```

Then register using the .bat file:
```cmd
schtasks /create ^
  /tn "ForexMorningAlert" ^
  /tr "\"C:\Users\Lenovo\OneDrive\Desktop\forex_factory_alert\run_alert.bat\"" ^
  /sc daily ^
  /st 06:30 ^
  /f
```

### Step 4: Verify the task is registered
```cmd
schtasks /query /tn "ForexMorningAlert" /fo LIST
```

### Step 5: Test with immediate trigger
```cmd
schtasks /run /tn "ForexMorningAlert"
```
Check `.tmp/scheduler_output.log` after ~2 minutes for output.

## Management Commands

| Action | Command |
|---|---|
| List task | `schtasks /query /tn "ForexMorningAlert" /fo LIST` |
| Run now | `schtasks /run /tn "ForexMorningAlert"` |
| Disable | `schtasks /change /tn "ForexMorningAlert" /disable` |
| Enable | `schtasks /change /tn "ForexMorningAlert" /enable` |
| Delete | `schtasks /delete /tn "ForexMorningAlert" /f` |

## Verify It Ran

After the scheduled time, check:
1. `.tmp/pipeline_log_YYYY-MM-DD.json` — step-by-step status
2. `.tmp/run_log_YYYY-MM-DD.json` — email delivery status
3. Your inbox — should have the morning email with PDF

## Troubleshooting

| Issue | Fix |
|---|---|
| Task fires but no email | Check `.tmp/run_log_*.json` for Gmail errors. Token may need refresh — delete `token.json` and re-run manually to trigger OAuth. |
| `ModuleNotFoundError` | The task is using a different Python than expected. Use the full path from `where python` in the .bat file. |
| Time zone confusion | Run `date /t` and `time /t` in CMD to see system time. Adjust `/st` accordingly. |
| `No active subscribers` | Run `python tools/manage_users.py --list` to verify users.db has entries. |
| PDF missing | Check `.tmp/pipeline_log_*.json` — if `pdf` step shows `failed`, run `python tools/generate_pdf_report.py` manually to see the error. |
