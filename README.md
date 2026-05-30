# TrustShield

**Real-time AI-powered fraud detection platform for UPI and digital payments**

TrustShield is a comprehensive fraud detection system that analyzes chat conversations in real-time to identify and prevent financial scams. It leverages NLP, graph-based entity analysis, and risk scoring to provide intelligent interventions and compliance reporting.

## Overview

TrustShield protects users from various types of digital fraud including:
- **Vishing** (Voice phishing)
- **Fake Support** (impersonating customer support)
- **Refund Scams** (QR code fraud, fake refund links)
- **OTP Harvesting** (soliciting one-time passwords)
- **Remote Access** (AnyDesk, TeamViewer exploitation)

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        TrustShield Platform                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Frontend   │  │   Backend    │  │   Android    │          │
│  │  (Next.js)   │  │  (FastAPI)   │  │    SDK       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                         │                                         │
│  ┌─────────────────────┴──────────────────────────────────────┐ │
│  │                    Core Services                             │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │ │
│  │  │    NLP       │  │   Graph      │  │ Intervention │      │ │
│  │  │  Processing  │  │   Analysis   │  │   Engine     │      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │ │
│  │  │   Risk       │  │ Compliance   │  │   Workers    │      │ │
│  │  │   Scoring    │  │   Reporting  │  │   (Celery)   │      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                         │                                         │
│  ┌─────────────────────┴──────────────────────────────────────┐ │
│  │                    Data Layer                                │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │ │
│  │  │  PostgreSQL  │  │   Neo4j      │  │   Redis      │      │ │
│  │  │  (Primary)   │  │  (Graph DB)  │  │  (Cache)     │      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │ │
│  │  ┌──────────────┐  ┌──────────────┐                         │ │
│  │  │   Kafka      │  │   MinIO      │                         │ │
│  │  │  (Events)    │  │  (Storage)   │                         │ │
│  │  └──────────────┘  └──────────────┘                         │ │
│  └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 14, TypeScript, React |
| **Backend** | FastAPI, Python 3.11+ |
| **Database** | PostgreSQL (with pgvector), Neo4j, Redis |
| **Messaging** | Apache Kafka |
| **Storage** | MinIO (object storage) |
| **ML** | ONNX Runtime, MuRIL (multilingual model) |
| **Deployment** | Docker, Docker Compose |
| **Mobile SDK** | Android (Kotlin) |

## Key Features

### 1. Real-time Analysis
- **<300ms latency** SLA for fraud detection
- Multi-language support (English, Hindi, Hinglish, mixed)
- Session-based context tracking

### 2. NLP Processing Pipeline
```
Input Text → Preprocessing → Entity Extraction → Scam Classification → Risk Scoring → Intervention
```

**Services:**
- `TextPreprocessor`: Cleans and normalizes input text
- `EntityExtractor`: Detects UPI IDs, phone numbers, remote access codes, IFSC codes, APK links
- `ScamClassifier`: ONNX-based model with MuRIL for multilingual classification
- `RiskScorer`: Multi-factor risk calculation (confidence, entities, context, history)

### 3. Graph-Based Analysis
- Neo4j-powered entity relationship mapping
- Fraud network visualization
- Risk propagation analysis
- Connected entity blacklisting

### 4. Intervention Engine
| Risk Level | Action | Description |
|------------|--------|-------------|
| LOW | NONE | No intervention |
| MEDIUM | SOFT_WARNING | Display warning message |
| HIGH | HARD_BLOCK | Block PIN entry temporarily |
| CRITICAL | FREEZE_AND_REPORT | Freeze transaction, report to 1930 |

### 5. Compliance & Reporting
- Automated RBI quarterly reports (PDF generation)
- 1930 helpline integration for critical cases
- Immutable audit trails to ELK stack
- False positive rate monitoring

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+ (for frontend)
- Android Studio (for SDK development)

### Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd TrustShield

# Start the development stack
make dev

# The following services will be available:
# - API: http://localhost:8000
# - Frontend: http://localhost:3000
# - Neo4j Browser: http://localhost:7474
# - MinIO Console: http://localhost:9001
```

### Manual Setup

```bash
# Start infrastructure services
cd infra
docker-compose up -d postgres neo4j redis kafka minio

# Start backend
cd ../backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start frontend
cd ../frontend
npm install
npm run dev

# Start workers
cd ../backend
celery -A app.workers.celery_app worker -l info
```

## API Documentation

### Analyze Endpoint

**POST** `/api/v1/analyze`

**Request:**
```json
{
  "messages": [
    {
      "sender": "agent",
      "text": "Please share your AnyDesk ID 123456789"
    }
  ],
  "session_metadata": {
    "client_app_id": "app_1",
    "session_id": "sess_1",
    "contact_initiated_by": "unknown",
    "is_during_active_upi_session": true,
    "user_device_hash": "hash1",
    "prior_reports_for_sender": 2
  }
}
```

**Response:**
```json
{
  "session_id": "sess_1",
  "risk_score": 85,
  "risk_level": "CRITICAL",
  "recommended_action": "FREEZE_AND_REPORT",
  "flagged_entities": [
    {
      "entity_type": "ANYDESK",
      "value": "123456789",
      "start_char": 32,
      "end_char": 41,
      "confidence_score": 0.99
    }
  ],
  "warning_message_en": "Warning: High risk of fraud! We have disabled PIN entry temporarily.",
  "warning_message_hi": "Chetawani: Fraud ka khatra! PIN entry kuch samay ke liye block kar diya hai.",
  "intervention_type": "FREEZE_AND_REPORT"
}
```

## Project Structure

```
TrustShield/
├── backend/               # FastAPI backend application
│   ├── app/              # Application code
│   │   ├── api/          # API endpoints
│   │   ├── models/       # Database models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic
│   │   ├── utils/        # Utility functions
│   │   └── workers/      # Background tasks
│   ├── ml/               # Machine learning
│   │   ├── data/         # Training data
│   │   └── training/     # Data augmentation
│   └── tests/            # Integration tests
├── frontend/             # Next.js frontend application
│   ├── app/              # Next.js app router pages
│   └── components/       # React components
├── infra/                # Infrastructure as code
│   └── docker-compose.yml
├── sdk/                  # Android SDK
│   └── android/
├── generate_dataset.py   # Dataset generator
├── Makefile              # Development commands
└── README.md
```

## Testing

```bash
# Run integration tests
make test

# Or manually
cd backend
PYTHONPATH=$(PWD)/backend pytest tests/integration/
```

## Development

### Data Augmentation

```bash
# Generate augmented training data
python generate_dataset.py
cd backend/ml/training
python augment_data.py
```

### RBI Report Generation

```bash
# Generate quarterly compliance report
python -m trustshield.backend.app.services.compliance.rbi_report_builder
```

## Monitoring & Observability

- **Logs**: ELK stack integration via Kafka
- **Metrics**: Custom metrics for risk scores, latency, false positives
- **Graph Visualization**: Neo4j Browser at `http://localhost:7474`
- **MinIO Console**: `http://localhost:9001`

## Compliance

TrustShield helps organizations meet RBI fraud detection mandates:
- Real-time fraud detection capability (<300ms latency)
- Immutable audit trails
- Entity blacklisting and reporting
- 1930 helpline integration for critical cases

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Contact

For support or questions, contact the TrustShield team.