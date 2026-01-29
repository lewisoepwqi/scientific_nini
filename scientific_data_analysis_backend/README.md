# Scientific Data Analysis Platform - Backend

A FastAPI-based backend for scientific data analysis, designed for researchers and scientists who need to analyze data and create publication-quality visualizations.

## Features

### Current Features
- **File Upload & Management**
  - Support for Excel (.xlsx, .xls), CSV, TSV files
  - Automatic data type detection
  - Data preview and basic statistics

- **Statistical Analysis**
  - Descriptive statistics (mean, std, percentiles, etc.)
  - T-tests (one-sample, independent, paired)
  - ANOVA (one-way with post-hoc tests)
  - Correlation analysis (Pearson, Spearman, Kendall)
  - Linear regression
  - Normality tests (Shapiro-Wilk)

- **Data Visualization**
  - Scatter plots with regression lines
  - Box plots and violin plots
  - Bar charts with error bars (Mean ± SEM)
  - Heatmaps (correlation matrices)
  - Paired line plots
  - Histograms
  - Academic journal color styles (Nature, Science, Cell, NEJM, Lancet)

### Planned Features
- **Experiment Design Assistant**
  - Sample size calculation (G*Power integration)
  - Power analysis
  - Experimental design recommendations

- **Multi-omics Support**
  - Single-cell RNA-seq analysis (Scanpy/Seurat workflows)
  - Gene expression visualization
  - Dimensionality reduction (PCA, t-SNE, UMAP)
  - Clustering analysis

- **AI-Powered Analysis**
  - Intelligent chart recommendations
  - Statistical test suggestions
  - Results interpretation
  - Natural language analysis queries

## Project Structure

```
scientific_data_analysis_backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── datasets.py       # Dataset upload & management
│   │       │   ├── analysis.py       # Statistical analysis endpoints
│   │       │   ├── visualizations.py # Chart generation endpoints
│   │       │   └── health.py         # Health check endpoints
│   │       └── router.py             # API router configuration
│   ├── core/
│   │   ├── config.py                 # Application configuration
│   │   └── exceptions.py             # Custom exceptions
│   ├── db/
│   │   └── base.py                   # Database configuration
│   ├── models/
│   │   ├── dataset.py                # Dataset model
│   │   ├── analysis.py               # Analysis & results models
│   │   └── visualization.py          # Visualization model
│   ├── schemas/
│   │   ├── common.py                 # Common schemas
│   │   ├── dataset.py                # Dataset schemas
│   │   ├── analysis.py               # Analysis schemas
│   │   └── visualization.py          # Visualization schemas
│   ├── services/
│   │   ├── file_service.py           # File upload handling
│   │   ├── data_service.py           # Data processing
│   │   ├── analysis_service.py       # Statistical analysis
│   │   ├── visualization_service.py  # Chart generation
│   │   └── ai_service.py             # AI assistance (placeholder)
│   ├── __init__.py
│   └── main.py                       # FastAPI application
├── uploads/                          # File upload directory
├── tests/                            # Test files
├── requirements.txt                  # Python dependencies
├── run.py                            # Development server
├── Dockerfile                        # Docker configuration
├── docker-compose.yml                # Docker Compose configuration
└── README.md                         # This file
```

## Quick Start

### Prerequisites
- Python 3.11+
- Redis (optional, for caching)

### Installation

1. Clone the repository:
```bash
cd scientific_data_analysis_backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create environment file:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Run the development server:
```bash
python run.py
```

The API will be available at `http://localhost:8000`

### Docker Deployment

```bash
docker-compose up -d
```

## API Documentation

Once the server is running, access the interactive API documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Main Endpoints

#### Datasets
- `POST /api/v1/datasets/upload` - Upload a data file
- `GET /api/v1/datasets/` - List all datasets
- `GET /api/v1/datasets/{id}` - Get dataset details
- `GET /api/v1/datasets/{id}/preview` - Preview dataset
- `GET /api/v1/datasets/{id}/stats` - Get column statistics
- `DELETE /api/v1/datasets/{id}` - Delete dataset

#### Analysis
- `POST /api/v1/analysis/descriptive` - Descriptive statistics
- `POST /api/v1/analysis/t-test` - T-test
- `POST /api/v1/analysis/anova` - ANOVA
- `POST /api/v1/analysis/correlation` - Correlation analysis
- `POST /api/v1/analysis/regression` - Linear regression
- `POST /api/v1/analysis/normality` - Normality test
- `GET /api/v1/analysis/types` - List available analysis types

#### Visualizations
- `POST /api/v1/visualizations/scatter` - Scatter plot
- `POST /api/v1/visualizations/box` - Box plot
- `POST /api/v1/visualizations/violin` - Violin plot
- `POST /api/v1/visualizations/bar` - Bar chart with error bars
- `POST /api/v1/visualizations/heatmap` - Heatmap
- `POST /api/v1/visualizations/paired` - Paired line plot
- `POST /api/v1/visualizations/histogram` - Histogram
- `GET /api/v1/visualizations/types` - List chart types
- `GET /api/v1/visualizations/journal-styles` - List journal styles

## Example Usage

### Upload a Dataset

```bash
curl -X POST "http://localhost:8000/api/v1/datasets/upload" \
  -H "accept: application/json" \
  -F "file=@data.xlsx" \
  -F "name=My Dataset"
```

### Perform T-Test

```bash
curl -X POST "http://localhost:8000/api/v1/analysis/t-test?dataset_id=xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "column": "value",
    "group_column": "group",
    "alternative": "two-sided"
  }'
```

### Create Scatter Plot

```bash
curl -X POST "http://localhost:8000/api/v1/visualizations/scatter?dataset_id=xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "x_column": "x",
    "y_column": "y",
    "show_regression": true,
    "journal_style": "nature"
  }'
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Enable debug mode | `false` |
| `DATABASE_URL` | Database connection URL | `sqlite+aiosqlite:///./scientific_data.db` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `MAX_UPLOAD_SIZE` | Maximum file upload size (bytes) | `104857600` (100MB) |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000` |

## Development

### Running Tests

```bash
pytest
```

### Code Style

```bash
# Format code
black app/

# Check types
mypy app/

# Lint
flake8 app/
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
