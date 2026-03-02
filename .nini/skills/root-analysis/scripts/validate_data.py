#!/usr/bin/env python3
"""
Data Validation Script for Plant Root Length Analysis

Validates CSV or Excel files to ensure they meet the requirements for
root length analysis with ANOVA and Tukey HSD testing.

Usage:
    python validate_data.py <data_file>

Output:
    JSON validation report with errors, warnings, and data summary
"""

import sys
import json
import argparse
from pathlib import Path
from collections import Counter

try:
    import pandas as pd
except ImportError:
    print(json.dumps({
        "valid": False,
        "errors": ["Required package 'pandas' not installed. Install with: pip install pandas"],
        "warnings": [],
        "summary": {}
    }))
    sys.exit(1)


def validate_data_file(file_path):
    """
    Validate a root length data file.

    Args:
        file_path: Path to CSV or Excel file

    Returns:
        dict: Validation report with keys: valid, errors, warnings, summary
    """
    errors = []
    warnings = []
    summary = {}

    file_path = Path(file_path)

    # Check 1: File exists and is readable
    if not file_path.exists():
        return {
            "valid": False,
            "errors": [f"File not found: {file_path}"],
            "warnings": [],
            "summary": {}
        }

    # Check 2: Read file based on extension
    try:
        if file_path.suffix.lower() == '.csv':
            data = pd.read_csv(file_path)
        elif file_path.suffix.lower() in ['.xlsx', '.xls']:
            data = pd.read_excel(file_path)
        else:
            errors.append(f"Unsupported file format: {file_path.suffix}. Use .csv, .xlsx, or .xls")
            return {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "summary": summary
            }
    except Exception as e:
        errors.append(f"Failed to read file: {str(e)}")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "summary": summary
        }

    # Check 3: Required columns exist
    required_columns = ['sample', 'treatment', 'length']
    missing_columns = [col for col in required_columns if col not in data.columns]

    if missing_columns:
        errors.append(
            f"Missing required columns: {', '.join(missing_columns)}. "
            f"Required: {', '.join(required_columns)}"
        )
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "summary": {"columns_found": list(data.columns)}
        }

    # Check 4: Length column is numeric
    try:
        data['length'] = pd.to_numeric(data['length'], errors='coerce')
        non_numeric_count = data['length'].isna().sum() - data.shape[0] + len(data)
        if non_numeric_count > 0:
            warnings.append(
                f"Found {non_numeric_count} non-numeric values in 'length' column. "
                "These will be treated as missing values."
            )
    except Exception as e:
        errors.append(f"Error converting 'length' column to numeric: {str(e)}")

    # Check 5: Treatment column validation
    treatments = data['treatment'].dropna().unique()

    # Check minimum number of treatments
    if len(treatments) < 2:
        errors.append(
            f"At least 2 treatment groups required. Found only: {', '.join(map(str, treatments))}"
        )

    # Recommend Mock group (warning if missing)
    if 'Mock' not in treatments:
        warnings.append(
            f"No 'Mock' control group found. For ratio analysis, 'Mock' is recommended. "
            f"Found treatments: {', '.join(map(str, treatments))}"
        )

    # Check 6: Check for missing values
    missing_counts = data[required_columns].isna().sum()
    total_missing = missing_counts.sum()

    if total_missing > 0:
        missing_pct = (total_missing / (len(data) * len(required_columns))) * 100
        warning_msg = f"Missing values detected: {missing_counts.to_dict()}"

        if missing_pct > 10:
            warnings.append(
                f"{warning_msg}. {missing_pct:.1f}% of data is missing. "
                "High missing rate may affect analysis quality."
            )
        else:
            warnings.append(f"{warning_msg}. These will be excluded from analysis.")

    # Check 7: Sample name consistency (detect spelling variations)
    sample_names = data['sample'].dropna().astype(str)
    sample_counts = Counter(sample_names)

    # Look for potential typos (samples with count < 3)
    low_count_samples = [s for s, c in sample_counts.items() if c < 3]
    if low_count_samples:
        warnings.append(
            f"Samples with fewer than 3 measurements: {', '.join(low_count_samples)}. "
            "Check for spelling inconsistencies or data collection issues."
        )

    # Check 8: Replication count per sample × treatment group
    if 'Mock' in treatments:
        clean_data = data.dropna(subset=required_columns)
        replication_counts = clean_data.groupby(['sample', 'treatment']).size()

        insufficient_reps = replication_counts[replication_counts < 3]
        if len(insufficient_reps) > 0:
            warnings.append(
                f"Some sample×treatment groups have fewer than 3 replicates:\n" +
                "\n".join([f"  {s[0]} × {s[1]}: {c} replicates"
                          for s, c in insufficient_reps.items()])
            )

    # Generate summary statistics
    clean_data = data.dropna(subset=required_columns)
    summary = {
        "n_samples": int(clean_data['sample'].nunique()),
        "sample_names": sorted(clean_data['sample'].unique().tolist()),
        "treatments": sorted(clean_data['treatment'].unique().tolist()),
        "n_measurements": int(len(clean_data)),
        "missing_values": int(total_missing),
        "length_range": {
            "min": float(clean_data['length'].min()),
            "max": float(clean_data['length'].max()),
            "mean": float(clean_data['length'].mean())
        }
    }

    # Determine overall validity
    valid = len(errors) == 0

    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "summary": summary
    }


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Validate root length data files for statistical analysis"
    )
    parser.add_argument(
        "data_file",
        help="Path to CSV or Excel file containing root length data"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Save validation report to file (default: print to stdout)"
    )

    args = parser.parse_args()

    # Validate the data
    report = validate_data_file(args.data_file)

    # Output results
    report_json = json.dumps(report, indent=2)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(report_json)
        print(f"Validation report saved to: {args.output}")
    else:
        print(report_json)

    # Exit with appropriate code
    sys.exit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
