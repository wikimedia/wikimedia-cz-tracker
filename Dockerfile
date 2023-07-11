# syntax=docker/dockerfile:1.4

FROM --platform=$BUILDPLATFORM python:3.9-alpine AS builder
EXPOSE 8000

RUN apk update && apk add --virtual build-deps gcc python3-dev musl-dev && apk add --no-cache bash mariadb-dev mariadb-client libffi-dev

COPY support/requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt --no-cache-dir
RUN apk del build-deps

RUN adduser -h /home/appuser -S appuser
WORKDIR /home/appuser

USER appuser

CMD ["python3", "trackersite/manage.py", "runserver", "0.0.0.0:8000"]