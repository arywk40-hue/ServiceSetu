# Run ServiceSetu on Windows

Use Python 3.10–3.13 and Git. Open PowerShell inside the repository:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-lock.txt -e '.[fetch]'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m servicesetu prove
```

Python 3.12 is also supported: replace `py -3.13` with `py -3.12`.
Windows requires the `tzdata` dependency for Asia/Kolkata appointment dates;
the project installation includes it automatically.

## Use existing registered identities

Put the owner's private `.env` beside `pyproject.toml`. Preserve
`SERVICESETU_SEED`; if it is blank, obtain the original private `data/agent-seed`
file. Do not run `prepare`, the mesh, or its proof with a missing original seed
if you need to preserve existing identities. Keep `.env` and `data/` private.

Stop the mesh on the other machine before starting the same identities here.
In PowerShell:

```powershell
$env:PYTHONUTF8 = '1'
$env:SERVICESETU_MAILBOX = 'true'
$env:PAYMENT_MODE = 'mock'
$demoDate = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::UtcNow, 'India Standard Time').ToString('yyyy-MM-dd')
$env:SERVICESETU_DB = "data/demo-$demoDate.db"
.\.venv\Scripts\python.exe -m servicesetu mesh
```

Keep the terminal open and the PC awake and online. Stop with Ctrl+C before
starting another copy. A new date selects a new database and fresh seeded slots;
an existing database preserves its original slots.

In a second PowerShell window inside the repository:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m servicesetu.register --verify
```

Expect 13 owned profiles and, after startup, 13 active Almanac entries.
Do not use `--apply` to recreate existing registrations.

To rerun the local proof while retaining the private seed and forcing offline
transport, use:

```powershell
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv(); import os; os.environ['SERVICESETU_MAILBOX']='false'; from servicesetu.__main__ import prove; prove()"
```

Open the Concierge's direct ASI:One link from the registration manifest, sign in,
and check that the recipient is ServiceSetu-concierge / @servicesetu. Ask for a
fictional AC service tomorrow at 10am in Indiranagar, Bengaluru under INR 1000.
Select a provider, review, approve the simulated payment, then ask
`show what happened`. This does not place a real service order.
