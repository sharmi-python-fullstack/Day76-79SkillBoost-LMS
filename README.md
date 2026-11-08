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

For production, set a unique `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, and `DJANGO_ALLOWED_HOSTS` for the deployment. Set `DB_ENGINE=mysql` and its credentials through environment variables when using MySQL, then run `python manage.py migrate` and `python manage.py collectstatic`. On a supported Linux server install the platform-specific Gunicorn dependency and run `gunicorn skillboost.wsgi`.

The committed settings use `DEBUG=False` by default and contain only a local-development fallback secret; always override it with a strong environment secret before deployment.
