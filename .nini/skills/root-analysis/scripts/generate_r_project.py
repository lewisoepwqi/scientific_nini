#!/usr/bin/env python3
"""
R Project Generation Script for Plant Root Length Analysis

Generates a complete R analysis project from templates with user configuration.

Usage:
    python generate_r_project.py --data-file <path> --color-scheme <scheme> [options]

Output:
    Creates R project directory with all necessary files configured
"""

import sys
import json
import argparse
import shutil
from pathlib import Path

try:
    from jinja2 import Template
except ImportError:
    print(json.dumps({
        "success": False,
        "error": "Required package 'jinja2' not installed. Install with: pip install jinja2"
    }))
    sys.exit(1)


class RProjectGenerator:
    """Generator for R analysis projects from templates."""

    VALID_COLOR_SCHEMES = ['default', 'high_contrast', 'blue', 'green', 'qualitative']

    def __init__(self, skill_dir):
        """
        Initialize generator.

        Args:
            skill_dir: Path to root-analysis skill directory
        """
        self.skill_dir = Path(skill_dir)
        self.template_dir = self.skill_dir / "scripts" / "r_templates"

    def generate_project(self, config):
        """
        Generate R project from templates.

        Args:
            config: dict with keys:
                - data_file: path to data file (required)
                - color_scheme: color scheme name (default: high_contrast)
                - sample_order: list of sample names or None for auto (default: None)
                - output_dir: output directory name (default: output)
                - plot_width: plot width in inches (default: 8)
                - plot_height: plot height in inches (default: 6)
                - project_dir: where to create project (default: ./r_analysis_project)

        Returns:
            dict: {success: bool, project_path: str, error: str (if failed)}
        """
        # Validate configuration
        validation_result = self._validate_config(config)
        if not validation_result["valid"]:
            return {
                "success": False,
                "error": validation_result["error"]
            }

        # Set defaults
        config.setdefault('color_scheme', 'high_contrast')
        config.setdefault('sample_order', None)
        config.setdefault('baseline_treatment', 'Mock')
        config.setdefault('output_dir', 'output')
        config.setdefault('plot_width', 8)
        config.setdefault('plot_height', 6)
        config.setdefault('project_dir', './r_analysis_project')

        project_path = Path(config['project_dir']).resolve()

        try:
            # Create project directory structure
            self._create_directory_structure(project_path)

            # Copy static R files
            self._copy_static_files(project_path)

            # Render and save main.R from template
            self._render_main_r(project_path, config)

            return {
                "success": True,
                "project_path": str(project_path),
                "message": f"R project created successfully at: {project_path}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to generate project: {str(e)}"
            }

    def _validate_config(self, config):
        """Validate configuration parameters."""
        # Check required fields
        if 'data_file' not in config:
            return {"valid": False, "error": "Missing required parameter: data_file"}

        # Check data file exists
        data_file = Path(config['data_file'])
        if not data_file.exists():
            return {"valid": False, "error": f"Data file not found: {config['data_file']}"}

        # Check color scheme
        color_scheme = config.get('color_scheme', 'high_contrast')
        if color_scheme not in self.VALID_COLOR_SCHEMES:
            return {
                "valid": False,
                "error": f"Invalid color scheme '{color_scheme}'. "
                        f"Valid options: {', '.join(self.VALID_COLOR_SCHEMES)}"
            }

        # Check plot dimensions
        for dim in ['plot_width', 'plot_height']:
            if dim in config:
                try:
                    val = float(config[dim])
                    if val <= 0:
                        return {"valid": False, "error": f"{dim} must be positive"}
                except (ValueError, TypeError):
                    return {"valid": False, "error": f"{dim} must be a number"}

        return {"valid": True}

    def _create_directory_structure(self, project_path):
        """Create R project directory structure."""
        # Create main directories
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "R").mkdir(exist_ok=True)
        (project_path / "output" / "figures").mkdir(parents=True, exist_ok=True)
        (project_path / "output" / "records").mkdir(parents=True, exist_ok=True)

    def _copy_static_files(self, project_path):
        """Copy static R files to project."""
        static_files = [
            "load_packages.R",
            "data_processing.R",
            "statistical_analysis.R",
            "plotting.R"
        ]

        r_dir = project_path / "R"

        for filename in static_files:
            src = self.template_dir / filename
            dst = r_dir / filename

            if not src.exists():
                raise FileNotFoundError(f"Template file not found: {src}")

            shutil.copy2(src, dst)

    def _render_main_r(self, project_path, config):
        """Render main.R from Jinja2 template."""
        template_path = self.template_dir / "main.R.jinja"

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Read template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        # Create Jinja2 template
        template = Template(template_content)

        # Convert data_file path to use forward slashes (R compatibility)
        data_file_path = Path(config['data_file']).resolve()
        data_file_str = str(data_file_path).replace('\\', '/')

        # Prepare template variables
        template_vars = {
            'data_file': data_file_str,
            'color_scheme': config['color_scheme'],
            'sample_order': config['sample_order'],  # None or list
            'baseline_treatment': config['baseline_treatment'],
            'output_dir': config['output_dir'],
            'plot_width': config['plot_width'],
            'plot_height': config['plot_height']
        }

        # Render template
        rendered = template.render(**template_vars)

        # Save rendered main.R
        main_r_path = project_path / "main.R"
        with open(main_r_path, 'w', encoding='utf-8') as f:
            f.write(rendered)


class PythonProjectGenerator:
    """Generator for Python analysis projects from templates."""

    VALID_COLOR_SCHEMES = ['default', 'high_contrast', 'blue', 'green', 'qualitative']

    def __init__(self, skill_dir):
        """
        Initialize generator.

        Args:
            skill_dir: Path to root-analysis skill directory
        """
        self.skill_dir = Path(skill_dir)
        self.template_dir = self.skill_dir / "scripts" / "python_templates"

    def generate_project(self, config):
        """
        Generate Python project from templates.

        Args:
            config: dict with configuration (same as R version)

        Returns:
            dict: {success: bool, project_path: str, error: str (if failed)}
        """
        # Validate configuration
        validation_result = self._validate_config(config)
        if not validation_result["valid"]:
            return {
                "success": False,
                "error": validation_result["error"]
            }

        # Set defaults
        config.setdefault('color_scheme', 'high_contrast')
        config.setdefault('sample_order', None)
        config.setdefault('baseline_treatment', 'Mock')
        config.setdefault('output_dir', 'output')
        config.setdefault('plot_width', 8)
        config.setdefault('plot_height', 6)
        config.setdefault('project_dir', './python_analysis_project')

        project_path = Path(config['project_dir']).resolve()

        try:
            # Create project directory structure
            self._create_directory_structure(project_path)

            # Copy static Python files
            self._copy_static_files(project_path)

            # Render and save main.py from template
            self._render_main_py(project_path, config)

            # Copy requirements.txt
            shutil.copy2(
                self.template_dir / "requirements.txt",
                project_path / "requirements.txt"
            )

            return {
                "success": True,
                "project_path": str(project_path),
                "message": f"Python项目创建成功: {project_path}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"生成项目失败: {str(e)}"
            }

    def _validate_config(self, config):
        """Validate configuration parameters."""
        # Check required fields
        if 'data_file' not in config:
            return {"valid": False, "error": "缺少必需参数: data_file"}

        # Check data file exists
        data_file = Path(config['data_file'])
        if not data_file.exists():
            return {"valid": False, "error": f"数据文件不存在: {config['data_file']}"}

        # Check color scheme
        color_scheme = config.get('color_scheme', 'high_contrast')
        if color_scheme not in self.VALID_COLOR_SCHEMES:
            return {
                "valid": False,
                "error": f"无效的颜色方案'{color_scheme}'。"
                        f"有效选项: {', '.join(self.VALID_COLOR_SCHEMES)}"
            }

        return {"valid": True}

    def _create_directory_structure(self, project_path):
        """Create Python project directory structure."""
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "output" / "figures").mkdir(parents=True, exist_ok=True)
        (project_path / "output" / "records").mkdir(parents=True, exist_ok=True)

    def _copy_static_files(self, project_path):
        """Copy static Python files to project."""
        static_files = [
            "analysis.py",
            "plotting.py"
        ]

        for filename in static_files:
            src = self.template_dir / filename
            dst = project_path / filename

            if not src.exists():
                raise FileNotFoundError(f"模板文件不存在: {src}")

            shutil.copy2(src, dst)

    def _render_main_py(self, project_path, config):
        """Render main.py from Jinja2 template."""
        template_path = self.template_dir / "main.py.jinja"

        if not template_path.exists():
            raise FileNotFoundError(f"模板不存在: {template_path}")

        # Read template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        # Create Jinja2 template
        template = Template(template_content)

        # Convert data_file path to use forward slashes
        data_file_path = Path(config['data_file']).resolve()
        data_file_str = str(data_file_path).replace('\\', '/')

        # Prepare template variables
        template_vars = {
            'data_file': data_file_str,
            'color_scheme': config['color_scheme'],
            'sample_order': config['sample_order'],  # None or list
            'baseline_treatment': config['baseline_treatment'],
            'output_dir': config['output_dir'],
            'plot_width': config['plot_width'],
            'plot_height': config['plot_height']
        }

        # Render template
        rendered = template.render(**template_vars)

        # Save rendered main.py
        main_py_path = project_path / "main.py"
        with open(main_py_path, 'w', encoding='utf-8') as f:
            f.write(rendered)


def parse_sample_order(order_str):
    """
    Parse sample order string.

    Args:
        order_str: comma-separated sample names or "auto"

    Returns:
        list of sample names or None for auto
    """
    if not order_str or order_str.lower() == "auto":
        return None

    # Split by comma and strip whitespace
    samples = [s.strip() for s in order_str.split(',')]
    return [s for s in samples if s]  # Remove empty strings


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Generate analysis project for root length data (R or Python)"
    )

    parser.add_argument(
        "--data-file",
        required=True,
        help="Path to CSV or Excel file with root length data"
    )

    parser.add_argument(
        "--color-scheme",
        choices=['default', 'high_contrast', 'blue', 'green', 'qualitative'],
        default='high_contrast',
        help="Color scheme for plots (default: high_contrast)"
    )

    parser.add_argument(
        "--sample-order",
        help='Sample order: "auto" or comma-separated list (e.g., "Col_0,mutant1,mutant2")'
    )

    parser.add_argument(
        "--baseline-treatment",
        default="Mock",
        help='Baseline treatment for ratio analysis (default: Mock)'
    )

    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory name within project (default: output)"
    )

    parser.add_argument(
        "--width",
        type=float,
        default=8,
        help="Plot width in inches (default: 8)"
    )

    parser.add_argument(
        "--height",
        type=float,
        default=6,
        help="Plot height in inches (default: 6)"
    )

    parser.add_argument(
        "--project-dir",
        help="Where to create project (default: auto based on --use-python)"
    )

    parser.add_argument(
        "--use-python",
        action="store_true",
        help="Generate Python project instead of R project"
    )

    parser.add_argument(
        "--skill-dir",
        help="Path to root-analysis skill directory (default: auto-detect)"
    )

    args = parser.parse_args()

    # Auto-detect skill directory if not provided
    if args.skill_dir:
        skill_dir = Path(args.skill_dir)
    else:
        # Assume script is in skill_dir/scripts/
        script_path = Path(__file__).resolve()
        skill_dir = script_path.parent.parent

    # Set default project directory based on mode
    if args.project_dir:
        project_dir = args.project_dir
    else:
        project_dir = "./python_analysis_project" if args.use_python else "./r_analysis_project"

    # Build configuration
    config = {
        'data_file': args.data_file,
        'color_scheme': args.color_scheme,
        'sample_order': parse_sample_order(args.sample_order),
        'baseline_treatment': args.baseline_treatment,
        'output_dir': args.output_dir,
        'plot_width': args.width,
        'plot_height': args.height,
        'project_dir': project_dir
    }

    # Create appropriate generator
    if args.use_python:
        generator = PythonProjectGenerator(skill_dir)
        # 输出到stderr，不影响stdout的JSON
        print("使用Python模式生成项目...", file=sys.stderr)
    else:
        generator = RProjectGenerator(skill_dir)
        print("使用R模式生成项目...", file=sys.stderr)

    # Generate project
    result = generator.generate_project(config)

    # Output result (only JSON to stdout)
    # Use ensure_ascii=True to avoid encoding issues in Windows console
    print(json.dumps(result, indent=2, ensure_ascii=True))

    # Exit with appropriate code
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
