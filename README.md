Сервис для сокращения ссылок с аналитикой и управлением(URL Shortener API).

Рабочий сервис: https://url-shortener-app-p5ro.onrender.com

Описание API:

1) Аутентификация

POST - /register - Регистрация нового пользователя

POST- `/login` - Вход в систему

POST - `/logout` - Выход из систему

2) Работа с ссылками
   
POST - `/links/shorten` - Создание короткой ссылки

GET - `/links/{short_code}` - Редирект на оригинальный URL

GET - `/links/{code}/stats` - Статистика по ссылке

PUT - `/links/{short_code}` - Обновление URL ссылки

DELETE - `/links/{short_code}`- Удаление ссылки

GET - `/links/search?original_url={url}` - Поиск по оригинальному URL

GET - `/links/expired/history` - История истекших ссылок

Примеры запросов

Регистрация
curl -X POST https://url-shortener-app-p5ro.onrender.com/register \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass"}'

Создание ссылки
curl -X POST https://url-shortener-app-p5ro.onrender.com/links/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://google.com"}'

Ответ
{"short_code": "bf8llp",
  "short_url": "https://url-shortener-app.onrender.com/links/bf8llp",
  "original_url": "https://google.com/",
  "clicks": 0}

Статистика
curl https://url-shortener-app-p5ro.onrender.com/links/bf8llp/stats

Ответ
{"short_code": "bf8llp",
  "clicks": 3,
  "last_accessed": "2026-03-09T08:12:33.041475",
  "original_url": "https://google.com/"}

  
Запуск через Docker
git clone https://github.com/Andrey-Mikhin/FastAPI_project.git
cd FastAPI_project
docker-compose up --build

Локально
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000


Описание базы данных
1) Таблица users
   
id- Integer -	Первичный ключ

username- 	String - Уникальное имя пользователя

password_hash- String- Хеш пароля

created_at - DateTime - Дата регистрации

2) Таблица links
   
id - Integer - Первичный ключ

short_code - String - Уникальный код ссылки

original_url - String - Оригинальный URL

custom_alias - String - Пользовательский алиас

created_at - DateTime - Дата создания

expires_at - DateTime - Дата истечения

clicks - Integer - Количество переходов

last_accessed - DateTime - Последний переход

is_active - Boolean - Активна ли ссылка

user_id - Integer - ID создателя

username - String - Имя создателя

Дополнительные улучшения

1) Мягкое удаление (soft delete) - Ссылки помечаются is_active=False, данные сохраняются
2) Разные причины в истории - reason: "expired" для истекших, "unused" для удаленных
3) Автоматическая фоновая очистка - Каждый час проверяет и чистит неиспользуемые ссылки
4) Хеширование паролей - HMAC-SHA256 для безопасного хранения 
   
