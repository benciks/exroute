FROM python:3.14

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY ./app /code/app

CMD ["fastapi", "run", "app/main.py", "--port", "8000"]
