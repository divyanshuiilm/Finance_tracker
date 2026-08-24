# Student Finance Manager

A local-first personal finance tracker for college students in India.

## Development setup

1. Install Python 3.12 or later from https://www.python.org/downloads/windows/.
2. During installation, select **Add python.exe to PATH**.
3. Open a new PowerShell window in this folder.
4. Create and activate the virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

5. Confirm the environment is ready:

   ```powershell
   python --version
   ```

The first Flask application will be created in Phase 2.

## Run automated checks

With the virtual environment activated, run:

```powershell
python -m unittest discover -s tests
```

The tests use a temporary database and do not change your `finance.db` file.
