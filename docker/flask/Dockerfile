FROM python:3.9 as base

COPY . /app/
COPY docker/flask/settings.json /app

WORKDIR /app
RUN pip install --upgrade pip \
    && pip install .

ENV INTERWEBZ_JSON_SETTINGS /app/settings.json
CMD ["gunicorn", "--workers=2", "--chdir=.", "--bind", "0.0.0.0:5000", "--access-logfile=-", "--error-logfile=-", "interwebz:create_app()"]
