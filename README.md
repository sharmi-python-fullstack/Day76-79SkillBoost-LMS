# SkillBoost LMS

A Django learning-management application with courses, video lessons, AI-generated quizzes, quiz scoring, completion tracking, certificates, and personalized course recommendations.

## Local setup (Windows PowerShell)

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set DJANGO_SECRET_KEY to a long random value.
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/` for the course catalog and `/admin/` for the Django admin. The default database is SQLite, so the app and tests can run without a MySQL server. To use MySQL, set `DB_ENGINE=mysql` and provide `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` in the process environment before running Django commands. `mysqlclient` is included in the requirements.

## AI features

Add your Gemini API key to the `GEMINI_API_KEY` line in your local `.env` file to enable quiz generation and recommendations. The settings load `.env` automatically, and `.env` is ignored by Git. Never put a real key in `.env.example` or commit it. The model name can be changed with `GEMINI_MODEL`. AI features return an explicit error when the key is missing or the API response cannot be used; ordinary course and quiz functionality does not require the API.

## Tests and deployment

Run the LMS test suite with:

```powershell
python manage.py test lms
```

### Deploy to Render

The app is configured for Render's PostgreSQL database through `DATABASE_URL` and serves collected static files with WhiteNoise.

1. Push the project to a GitHub repository. Do not commit `.env`; it is excluded by `.gitignore`. Check that `.env.example` contains placeholders only.
2. In Render, create a managed PostgreSQL database. Copy its **internal** connection URL from the database's Connect details.
3. Create a **Web Service** from your GitHub repository. Use:
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate && python manage.py bootstrap_admin`
   - **Start command:** `python -m gunicorn skillboost.wsgi:application`
4. In the web service's environment settings, add:
   - `DATABASE_URL`: the database's internal URL
   - `DJANGO_SECRET_KEY`: generate a new, long random value
   - `DJANGO_DEBUG`: `False`
   - `DJANGO_ALLOWED_HOSTS`: your Render hostname, such as `skillboost-example.onrender.com`
   - `GEMINI_API_KEY`: your current Gemini key (optional; do not commit it)
   - `GEMINI_MODEL`: `gemini-3.5-flash-lite`
   - `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD`: set these temporarily to create the first admin during the build. Use a unique, strong password.
5. Deploy. Visit the generated `https://...onrender.com` address and sign in at `/admin/` with the temporary admin credentials. Once the deploy succeeds, remove the three `DJANGO_SUPERUSER_*` variables from Render and redeploy. The bootstrap command safely skips when credentials are absent and does not change an existing account's password.

Render's filesystem is not persistent for ordinary web services. PostgreSQL keeps database records across deploys; do not rely on SQLite or local filesystem uploads for production data.

For production, use a unique secret, keep `DEBUG=False`, and use the database connection URL from the deployment provider. On a supported Linux server the app runs with `gunicorn skillboost.wsgi:application`.

The committed settings use `DEBUG=False` by default and contain only a local-development fallback secret; always override it with a strong environment secret before deployment.
