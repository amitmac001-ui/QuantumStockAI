web: python manage.py migrate --noinput --settings=config.settings.production && python manage.py collectstatic --noinput --settings=config.settings.production && DJANGO_SETTINGS_MODULE=config.settings.production daphne -b 0.0.0.0 -p $PORT config.asgi:application
quote-worker: python manage.py sync_quotes --interval 5 --settings=config.settings.production
