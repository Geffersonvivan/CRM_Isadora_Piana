web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn crm_sorgatto.wsgi --bind 0.0.0.0:$PORT
