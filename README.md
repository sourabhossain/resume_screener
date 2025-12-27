# ResumeAI - AI-Powered Resume Screening System

Intelligent resume screening system that uses **LangGraph** and **OpenAI GPT** to automatically analyze, score, and rank candidates against job requirements.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Django](https://img.shields.io/badge/Django-5.2-green)
![LangGraph](https://img.shields.io/badge/LangGraph-AI-purple)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)

---

## ✨ Features

| Category           | Features                                                                |
| ------------------ | ----------------------------------------------------------------------- |
| **AI Screening**   | 🤖 Automatic resume parsing & skill extraction                          |
|                    | 🎯 Job-resume matching with scoring                                     |
|                    | 📊 Multi-factor scoring (Skills, Experience, Education, Certifications) |
|                    | 🏆 Tier-based ranking (Top/Mid/Low) with recommendations                |
| **Job Management** | 📋 Full CRUD for job postings                                           |
|                    | 📁 PDF/DOCX resume uploads                                              |
|                    | 🔍 Search & filter functionality                                        |
| **UI/UX**          | 🌙 Dark mode support                                                    |
|                    | 📱 Mobile responsive design                                             |
|                    | ⚡ HTMX-powered dynamic interactions                                    |
| **Developer**      | 🔌 REST API with DRF                                                    |
|                    | 🔐 Session-based authentication                                         |
|                    | 🧪 Pytest test suite                                                    |

---

## 🤖 AI Screening Pipeline

The system uses a **LangGraph state machine** to process resumes through 4 stages:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   EXTRACT    │────▶│    MATCH     │────▶│    SCORE     │────▶│    RANK      │
│              │     │              │     │              │     │              │
│ Parse resume │     │ Compare with │     │ Calculate    │     │ Assign tier  │
│ Extract:     │     │ job reqs:    │     │ weighted     │     │ & suggest    │
│ • Skills     │     │ • Matched    │     │ scores       │     │ action       │
│ • Education  │     │ • Missing    │     │              │     │              │
│ • Experience │     │ • Gaps       │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Scoring Weights

| Factor         | Weight | Description                  |
| -------------- | ------ | ---------------------------- |
| Skills         | 40%    | Matched skills vs required   |
| Experience     | 30%    | Years of relevant experience |
| Education      | 20%    | Education level match        |
| Certifications | 10%    | Relevant certifications      |

### Tier & Recommendations

| Final Score | Tier       | Recommendation |
| ----------- | ---------- | -------------- |
| 80-100      | 🏆 **Top** | ✅ Interview   |
| 60-79       | 🥈 **Mid** | 📁 Talent Pool |
| 0-59        | 🥉 **Low** | ❌ Reject      |

---

## 🐳 Quick Start (Docker)

### Prerequisites

- Docker & Docker Compose
- OpenAI API Key

### Setup

```bash
# 1. Clone & navigate
git clone git@github.com:sourabhossain/resume_screener.git
cd resume_screening_system

# 2. Configure environment
cp .env.example .env
```

Edit `.env`:

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

# OpenAI (Required)
OPENAI_API_KEY=sk-your-openai-api-key

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

```bash
# 3. Build & start
docker-compose up -d --build

# 4. Run migrations
docker-compose exec web python manage.py migrate

# 5. Create admin user
docker-compose exec web python manage.py createsuperuser

# 6. Collect static files
docker-compose exec web python manage.py collectstatic --noinput
```

### Access Points

| Service         | URL                   | Credentials                |
| --------------- | --------------------- | -------------------------- |
| **Web App**     | http://localhost:8000 | Your superuser             |
| **Nginx Proxy** | http://localhost      | -                          |
| **pgAdmin**     | http://localhost:5050 | `admin@admin.com` / `root` |

---

## 🏗️ Architecture

```
                           ┌─────────────────────┐
                           │   Browser (User)    │
                           │  HTMX + Alpine.js   │
                           └──────────┬──────────┘
                                      │
┌─────────────────────────────────────┼─────────────────────────────────────┐
│                                     ▼                                     │
│  ┌─────────────┐              ┌─────────────┐              ┌───────────┐  │
│  │   Nginx     │─────────────▶│   Django    │─────────────▶│ PostgreSQL│  │
│  │   :80       │              │   :8000     │              │   :5433   │  │
│  └─────────────┘              └──────┬──────┘              └───────────┘  │
│                                      │                                    │
│                               ┌──────▼──────┐                             │
│                               │   Celery    │◀────────┐                   │
│                               │   Worker    │         │                   │
│                               └──────┬──────┘         │                   │
│                                      │          ┌─────┴─────┐             │
│                               ┌──────▼──────┐   │   Redis   │             │
│                               │  OpenAI API │   │   :6379   │             │
│                               │  (GPT-4o)   │   └───────────┘             │
│                               └─────────────┘                             │
│                                                                           │
│  Docker Compose                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
resume_screening_system/
├── apps/core/
│   ├── models.py           # Job, Resume models
│   ├── views.py            # UI views
│   ├── api_views.py        # REST API viewsets
│   ├── forms.py            # Django forms
│   ├── tasks.py            # Celery async tasks
│   ├── services/
│   │   ├── ai_screener.py      # LangGraph pipeline
│   │   ├── llm_client.py       # OpenAI client
│   │   ├── document_extractor.py # PDF/DOCX parser
│   │   └── resume_service.py   # Business logic
│   ├── prompts/            # AI prompt templates
│   └── tests/              # Unit tests
├── config/
│   ├── settings/           # Django settings (base, dev, prod)
│   ├── celery.py           # Celery configuration
│   └── urls.py             # URL routing
├── templates/              # HTML templates
├── static/                 # Static assets
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
└── requirements.txt
```

---

## 🔌 REST API

### Endpoints

| Method   | Endpoint                 | Description           |
| -------- | ------------------------ | --------------------- |
| `GET`    | `/api/jobs/`             | List all jobs         |
| `POST`   | `/api/jobs/`             | Create job            |
| `GET`    | `/api/jobs/{id}/`        | Get job details       |
| `PUT`    | `/api/jobs/{id}/`        | Update job            |
| `DELETE` | `/api/jobs/{id}/`        | Delete job            |
| `GET`    | `/api/resumes/`          | List all resumes      |
| `GET`    | `/api/resumes/?job={id}` | Filter resumes by job |
| `POST`   | `/api/resumes/`          | Upload resume         |

### API Documentation

Interactive API docs available at:

- **Swagger UI**: `/api/schema/swagger-ui/`
- **ReDoc**: `/api/schema/redoc/`

---

## 🧪 Testing

```bash
# Run all tests
docker-compose exec web pytest

# With coverage report
docker-compose exec web pytest --cov=apps --cov-report=html

# Specific test file
docker-compose exec web pytest apps/core/tests/test_models.py -v
```

---

## 🛠️ Common Commands

```bash
# Container management
docker-compose up -d              # Start all services
docker-compose down               # Stop all services
docker-compose restart web celery # Restart web & celery

# Logs
docker-compose logs -f web        # Django logs
docker-compose logs -f celery     # Celery worker logs

# Django management
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py shell
docker-compose exec web python manage.py collectstatic

# Rebuild after requirements change
docker-compose build --no-cache web celery
docker-compose up -d
```

---

## 🔧 Troubleshooting

| Issue                     | Solution                                                              |
| ------------------------- | --------------------------------------------------------------------- |
| Database connection error | `docker-compose restart db` and wait for healthy status               |
| Celery not processing     | Check `docker-compose logs celery` for errors                         |
| Static files 404          | Run `docker-compose exec web python manage.py collectstatic`          |
| AI screening fails        | Verify `OPENAI_API_KEY` in `.env` is valid                            |
| Redis connection error    | Check `CELERY_BROKER_URL` uses `redis://redis:6379/0` (not localhost) |

---

## 📦 Tech Stack

| Layer        | Technologies                                    |
| ------------ | ----------------------------------------------- |
| **Backend**  | Django 5.2, Django REST Framework, Celery       |
| **AI/ML**    | LangGraph, LangChain, OpenAI GPT                |
| **Database** | PostgreSQL 15, Redis 7                          |
| **Frontend** | Django Templates, HTMX, Alpine.js, Tailwind CSS |
| **DevOps**   | Docker, Docker Compose, Nginx                   |
| **Testing**  | Pytest, Factory Boy                             |

---

## 📝 License

MIT License
