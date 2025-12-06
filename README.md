# ResumeAI - Resume Screening System

AI-powered resume screening system built with Django, PostgreSQL, and Docker.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Django](https://img.shields.io/badge/Django-5.0-green)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)

## Features

- 📋 Job posting management (CRUD)
- 📄 Resume upload and screening
- 🎯 Auto tier & recommendation based on scores
- 🔍 Search & filter functionality
- 🌙 Dark mode support
- 📱 Mobile responsive design
- 🔐 User authentication
- 🔌 REST API

---

## 🐳 Docker Setup

### Prerequisites

- Docker & Docker Compose
- Git
- OpenAI API Key (AI স্ক্রীনিং ফিচারের জন্য)

### Quick Start

```bash
# 1. Clone the repository
git clone git@github.com:sourabhossain/resume_screener.git
cd resume_screening_system

# 2. Environment setup
cp .env.example .env
```

`.env` ফাইলে নিচের ভ্যালুগুলো সেট করুন:

```env
# Database
DB_NAME=resume_db
DB_USER=postgres
DB_PASSWORD=your_secure_password
DB_HOST=db
DB_PORT=5433

# Django
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1

# OpenAI (Required for AI screening)
OPENAI_API_KEY=sk-your-openai-api-key

# Celery (Redis)
CELERY_BROKER_URL=redis://redis:6379/0
```

```bash
# 3. Build & Start
docker-compose up -d --build

# 4. Database setup
docker-compose exec web python manage.py migrate

# 5. Create admin user
docker-compose exec web python manage.py createsuperuser
```

### Access Points

| Service | URL                   | Description       |
| ------- | --------------------- | ----------------- |
| Web App | http://localhost:8000 | Main application  |
| Nginx   | http://localhost:80   | Production proxy  |
| pgAdmin | http://localhost:5050 | Database admin UI |

**pgAdmin Credentials:** `admin@admin.com` / `root`

### Services Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Nginx     │────▶│   Django    │────▶│  PostgreSQL │
│   (Port 80) │     │  (Port 8000)│     │  (Port 5433)│
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │
                    ┌─────▼─────┐     ┌─────────────┐
                    │  Celery   │────▶│    Redis    │
                    │  Worker   │     │ (Port 6379) │
                    └───────────┘     └─────────────┘
```

### Common Commands

```bash
# Container management
docker-compose up -d          # Start all services
docker-compose down           # Stop all services
docker-compose restart web    # Restart specific service

# Logs
docker-compose logs -f web    # Django logs
docker-compose logs -f celery # Celery worker logs

# Django commands
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py shell
docker-compose exec web python manage.py collectstatic

# Testing
docker-compose exec web pytest
docker-compose exec web pytest --cov=apps

# Rebuild (after changing requirements.txt)
docker-compose build --no-cache web celery
docker-compose up -d
```

### Troubleshooting

| Issue                     | Solution                                                 |
| ------------------------- | -------------------------------------------------------- |
| Database connection error | `docker-compose restart db` এবং health check দেখুন       |
| Celery not processing     | `docker-compose logs celery` দেখুন                       |
| Static files missing      | `docker-compose exec web python manage.py collectstatic` |

---

## 🔌 REST API

### Endpoints

| Method | Endpoint              | Description      |
| ------ | --------------------- | ---------------- |
| GET    | `/api/jobs/`          | List all jobs    |
| POST   | `/api/jobs/`          | Create new job   |
| GET    | `/api/jobs/{id}/`     | Get job details  |
| PUT    | `/api/jobs/{id}/`     | Update job       |
| DELETE | `/api/jobs/{id}/`     | Delete job       |
| GET    | `/api/resumes/`       | List all resumes |
| GET    | `/api/resumes/?job=1` | Filter by job    |

### Authentication

Session-based authentication required. Login at `/login/` first.

---

## 📁 Project Structure

```
resume_screening_system/
├── apps/
│   └── core/           # Main application
│       ├── models.py   # Job, Resume models
│       ├── views.py    # View functions
│       ├── forms.py    # Django forms
│       ├── api_views.py # DRF viewsets
│       └── tests/      # Unit tests
├── config/
│   ├── settings/       # Django settings
│   └── urls.py         # URL routing
├── templates/          # HTML templates
├── docker-compose.yml  # Docker config
├── Dockerfile
└── requirements.txt
```

---

## 🧪 Running Tests

```bash
# With Docker
docker-compose exec web pytest

# With coverage
docker-compose exec web pytest --cov=apps

# Specific test file
docker-compose exec web pytest apps/core/tests/test_models.py
```

---

## 📝 License

MIT License
