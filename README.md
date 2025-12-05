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

## 🐳 Docker Setup (Recommended)

### Prerequisites

- Docker & Docker Compose installed
- Git

### Quick Start

```bash
# 1. Clone the repository
git clone <repository-url>
cd resume_screening_system

# 2. Create .env file
cp .env.example .env
# Edit .env with your settings

# 3. Build and start containers
docker-compose up -d --build

# 4. Run migrations
docker-compose exec web python manage.py migrate

# 5. Create superuser
docker-compose exec web python manage.py createsuperuser

# 6. Access the application
# Web App: http://localhost:8000
# pgAdmin: http://localhost:5050
```

### Environment Variables (.env)

```env
# Database
DB_NAME=resume_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=db
DB_PORT=5433

# Django
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Docker Commands

```bash
# Start containers
docker-compose up -d

# Stop containers
docker-compose down

# View logs
docker-compose logs -f web

# Rebuild after requirements change
docker-compose build --no-cache
docker-compose up -d

# Run tests
docker-compose exec web pytest

# Django shell
docker-compose exec web python manage.py shell

# Create migrations
docker-compose exec web python manage.py makemigrations
```

### Services

| Service | Port | Description         |
| ------- | ---- | ------------------- |
| web     | 8000 | Django application  |
| db      | 5433 | PostgreSQL database |
| pgadmin | 5050 | Database admin UI   |

### pgAdmin Login

- **Email:** admin@admin.com
- **Password:** root
- **DB Password:** (from your .env DB_PASSWORD)

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
