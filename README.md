# Academic Risk & Student Performance Intelligence System

A college mini-project (Flask + SQLite) that helps teachers spot students who may need
academic support, using attendance, marks and assignment completion.
It supports academic support decisions; it does not predict a student's future.

**Status: Milestone 1 (Foundation) complete. Milestone 2, Stage 1 (admin: students, teachers, courses, teacher assignment, enrolment) built; awaiting review.**

Updating from the Milestone 1 version? The database schema did not change, so your existing `instance/academic_risk.db` keeps working. Copy the new files over, run `pip install -r requirements.txt` (no new packages) and `python -m pytest`.

## Internet requirement (important for the demo machine)

Bootstrap 5.3.3 (CSS and JS) is loaded from the **jsDelivr CDN** (`cdn.jsdelivr.net`).
Chart.js (added in Milestone 3) will also load from a CDN.
**The computer used for the presentation needs internet access**, otherwise pages
work but look unstyled. Test this before your demo.

## Windows setup (Python 3.12 or 3.13)

Open a terminal in the project folder (the one containing `run.py`).

**1. Check Python**
```
py --version
```

**2. Create and activate a virtual environment**

Command Prompt (CMD):
```
py -m venv venv
venv\Scripts\activate
```
PowerShell:
```
py -m venv venv
.\venv\Scripts\Activate.ps1
```
If PowerShell says "running scripts is disabled", run this once, then activate again:
```
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
When active, your prompt starts with `(venv)`.

**3. Install dependencies**
```
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**4. Create the database**
```
python init_db.py
```

**5. Add the demo accounts**
```
python seed.py
```

**6. Run the app**
```
python run.py
```
Open http://127.0.0.1:5000 in your browser. Stop the server with `Ctrl+C`.

**Run the tests**
```
python -m pytest
```

**Reset the database** (stop the server first):
```
del instance\academic_risk.db
python init_db.py
python seed.py
```
Do this whenever someone changes `app/models.py`, because `init_db.py` does not
alter tables that already exist.

## Demo accounts (LOCAL DEMONSTRATION ONLY)

These are **synthetic accounts with publicly written passwords**. Use them only on your
own computer for the demo. Never use them, or these passwords, for anything real.

| Role | Email | Password |
|---|---|---|
| Administrator | admin@college.test | Admin@123 |
| Teacher 1 | teacher1@college.test | Teacher@123 |
| Teacher 2 | teacher2@college.test | Teacher@123 |
| Teacher 3 | teacher3@college.test | Teacher@123 |

Passwords are stored as hashes in the database, not as plain text.

## Security settings (Phase 15)

`python run.py` works exactly as before for the local demonstration. For any real
deployment set `APP_ENV=production` and a long random `SECRET_KEY`; the application
refuses to start in production with the default key or with debug enabled. Details,
security headers and the audit findings are in `docs/PHASE15_SECURITY.md`.

## Project layout

```
academic_risk/
  run.py            start the server
  init_db.py        create tables
  seed.py           add demo accounts (safe to run repeatedly)
  config.py         settings (secret key, database, cookies)
  requirements.txt
  pytest.ini
  app/
    __init__.py     create_app(): sets up extensions, blueprints, error pages
    models.py       all 10 database tables
    forms.py        Flask-WTF forms
    auth.py         login / logout
    admin.py        administrator pages
    teacher.py      teacher pages
    reports.py      shared reports (Milestone 3)
    templates/      HTML (base.html is the layout every page extends)
    static/css/     style.css
  tests/            pytest tests
  docs/             ROUTES.md (route table), FOUNDATION.md, MILESTONE2_STAGE1.md
```
`app/risk_engine.py` (all risk calculations, no Flask code) is added in Milestone 3.

## Git workflow

- `main` always holds a working app. Work on feature branches:
  `feature/auth`, `feature/attendance-marks`, `feature/assignments-risk`, `feature/dashboard-ui`.
- **Do not edit `app/models.py` without telling the team.** Agree the change, one person
  edits, everyone pulls.
- Before merging to `main`: run `python -m pytest` and click through the app.
- Never commit `venv/`, `instance/`, `*.db` or `.env` (already in `.gitignore`).

First-time setup for the team (one person):
```
git init
git add .
git commit -m "Milestone 1: foundation"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```
