# pishem-text-backend

Минимальный Flask API для аккаунтов и сохранения работ редактора «Текстер PRO».

## Локальный запуск

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Проверка: http://127.0.0.1:8000/api/health

## Timeweb

Точка входа WSGI: `wsgi:application`.

Переменные окружения:

- `SECRET_KEY` — длинная случайная строка;
- `FRONTEND_ORIGIN=https://yalica.github.io`;
- `PORT` — порт, если его задаёт панель.

`DATABASE_PATH` указывать не нужно: приложение само создаст
`instance/app.sqlite3` рядом с собой на сервере.
