FROM python:3.14

LABEL org.opencontainers.image.source="https://github.com/benciks/exroute"

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app
COPY ./alembic.ini /code/alembic.ini
COPY ./alembic /code/alembic

CMD ["fastapi", "run", "app/main.py", "--port", "8000"]
