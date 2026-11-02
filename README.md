# Local Service Request Tracking Portal

Full stack project (Django + PostgreSQL).
**Individual focus: Service assignment and status tracking.**

## Roles
| Role | Can do |
|------|--------|
| Customer | Raise requests, track status, cancel while Pending/Assigned |
| Admin / Dispatcher | See all requests, assign or reassign providers, cancel, unassign |
| Service Provider | See only own jobs, start work, complete, or decline a job |

## Status workflow (state machine in `tracker/models.py`)
```
Pending -> Assigned -> In Progress -> Completed
   |          |  \-> Pending (provider declines / admin unassigns)
   \-> Cancelled <-/
```
Invalid jumps (e.g. Pending -> Completed) are rejected. Every change is saved in `StatusHistory` (who, when, note) and shown as a timeline.

## Run it
```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
```
**Use PostgreSQL:** create a database (`CREATE DATABASE service_portal;`) then set:
```bash
set DB_NAME=service_portal
set DB_USER=postgres
set DB_PASSWORD=yourpassword
```
(Linux/Mac: `export` instead of `set`). If `DB_NAME` is not set, it uses SQLite so you can try it instantly.

```bash
python manage.py migrate
python manage.py seed_demo         # optional demo users + requests
python manage.py runserver
```
Open http://127.0.0.1:8000 . Demo logins (password `demo12345`): `dispatcher`, `ravi_plumber`, `meena_electric`, `asha`.

Run tests: `python manage.py test`

## Structure
- `tracker/models.py` – User (roles), ServiceRequest (workflow + `assign_to` / `change_status`), StatusHistory
- `tracker/views.py` – role-based dashboard, assignment, status update
- `tracker/forms.py`, `tracker/templates/` – UI
- `tracker/tests.py` – 19 tests (workflow rules + permissions)
