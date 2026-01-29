# API Documentation

Complete API reference for the Scientific Data Analysis Platform.

## Base URL
```
http://localhost:8000/api/v1
```

## Authentication
Currently, the API does not require authentication. Future versions will include JWT-based authentication.

---

## Datasets

### Upload Dataset
Upload a new data file (Excel, CSV, or TSV).

```http
POST /datasets/upload
```

**Request Body (multipart/form-data):**
- `file` (required): Data file (.xlsx, .xls, .csv, .tsv, .txt)
- `name` (optional): Custom name for the dataset
- `description` (optional): Dataset description

**Response:**
```json
{
  "success": true,
  "message": "Dataset uploaded successfully",
  "data": {
    "id": "uuid",
    "name": "Dataset Name",
    "filename": "data.xlsx",
    "file_size": 1024,
    "file_type": "xlsx",
    "row_count": 100,
    "column_count": 5,
    "created_at": "2024-01-01T00:00:00"
  }
}
```

### List Datasets
```http
GET /datasets/?skip=0&limit=100
```

### Get Dataset
```http
GET /datasets/{dataset_id}
```

### Get Dataset Preview
```http
GET /datasets/{dataset_id}/preview?rows=10
```

### Get Dataset Statistics
```http
GET /datasets/{dataset_id}/stats
```

### Get Dataset Columns
```http
GET /datasets/{dataset_id}/columns
```

### Update Dataset
```http
PUT /datasets/{dataset_id}
Content-Type: application/json

{
  "name": "New Name",
  "description": "Updated description"
}
```

### Delete Dataset
```http
DELETE /datasets/{dataset_id}
```

---

## Analysis

### Descriptive Statistics
```http
POST /analysis/descriptive?dataset_id={id}
Content-Type: application/json

{
  "columns": ["col1", "col2"],
  "group_by": "group_col",
  "include_percentiles": [0.25, 0.5, 0.75]
}
```

### T-Test
```http
POST /analysis/t-test?dataset_id={id}
Content-Type: application/json

{
  "column": "value_col",
  "group_column": "group_col",
  "alternative": "two-sided",
  "paired": false,
  "confidence_level": 0.95
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "statistic": 2.5,
    "pvalue": 0.015,
    "df": 48,
    "confidence_interval": [0.5, 4.5],
    "effect_size": 0.71,
    "mean_diff": 2.5,
    "std_diff": 1.0
  }
}
```

### ANOVA
```http
POST /analysis/anova?dataset_id={id}
Content-Type: application/json

{
  "value_column": "value_col",
  "group_columns": ["group_col"],
  "post_hoc": true,
  "post_hoc_method": "tukey"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "f_statistic": 5.23,
    "pvalue": 0.008,
    "df_between": 2,
    "df_within": 57,
    "sum_sq_between": 100.5,
    "sum_sq_within": 548.2,
    "mean_sq_between": 50.25,
    "mean_sq_within": 9.62,
    "eta_squared": 0.15,
    "post_hoc_results": [...]
  }
}
```

### Correlation Analysis
```http
POST /analysis/correlation?dataset_id={id}
Content-Type: application/json

{
  "columns": ["col1", "col2", "col3"],
  "method": "pearson"
}
```

### Linear Regression
```http
POST /analysis/regression?dataset_id={id}
Content-Type: application/json

{
  "dependent_var": "y_col",
  "independent_vars": ["x1", "x2"],
  "include_intercept": true
}
```

### Normality Test
```http
POST /analysis/normality?dataset_id={id}&column=value_col
```

### List Analysis Types
```http
GET /analysis/types
```

---

## Visualizations

### Scatter Plot
```http
POST /visualizations/scatter?dataset_id={id}
Content-Type: application/json

{
  "x_column": "x",
  "y_column": "y",
  "color_column": "group",
  "show_regression": true,
  "show_equation": true,
  "show_r_squared": true,
  "journal_style": "nature",
  "width": 800,
  "height": 600
}
```

### Box Plot
```http
POST /visualizations/box?dataset_id={id}
Content-Type: application/json

{
  "value_column": "value",
  "group_column": "group",
  "show_points": true,
  "show_mean": true,
  "journal_style": "science"
}
```

### Violin Plot
```http
POST /visualizations/violin?dataset_id={id}
Content-Type: application/json

{
  "value_column": "value",
  "group_column": "group",
  "show_box": true,
  "journal_style": "cell"
}
```

### Bar Chart with Error Bars
```http
POST /visualizations/bar?dataset_id={id}
Content-Type: application/json

{
  "x_column": "group",
  "y_column": "value",
  "error_type": "sem",
  "journal_style": "nejm"
}
```

**Error Types:**
- `sem`: Standard Error of Mean
- `sd`: Standard Deviation
- `ci`: 95% Confidence Interval

### Heatmap
```http
POST /visualizations/heatmap?dataset_id={id}
Content-Type: application/json

{
  "columns": ["col1", "col2", "col3"],
  "colorscale": "RdBu_r",
  "center_at_zero": true,
  "show_values": true
}
```

### Paired Line Plot
```http
POST /visualizations/paired?dataset_id={id}
Content-Type: application/json

{
  "subject_column": "subject_id",
  "condition_column": "condition",
  "value_column": "value",
  "show_mean_line": true
}
```

### Histogram
```http
POST /visualizations/histogram?dataset_id={id}
Content-Type: application/json

{
  "column": "value",
  "group_column": "group",
  "bins": 30,
  "journal_style": "lancet"
}
```

### List Chart Types
```http
GET /visualizations/types
```

### List Journal Styles
```http
GET /visualizations/journal-styles
```

**Available Styles:**
- `nature`: Nature journal palette
- `science`: Science journal palette
- `cell`: Cell journal palette
- `nejm`: New England Journal of Medicine palette
- `lancet`: Lancet journal palette
- `default`: Default Plotly palette

---

## Health Check

### Health Status
```http
GET /health/
```

### Ping
```http
GET /health/ping
```

---

## Response Format

All API responses follow a consistent format:

### Success Response
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": { ... }
}
```

### Error Response
```json
{
  "success": false,
  "message": "Error description",
  "error_code": "ERROR_CODE",
  "details": { ... }
}
```

## HTTP Status Codes

- `200`: Success
- `201`: Created
- `400`: Bad Request
- `404`: Not Found
- `422`: Unprocessable Entity
- `500`: Internal Server Error

## Rate Limiting

Future versions will implement rate limiting. Currently, no limits are enforced.
