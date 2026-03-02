#!/usr/bin/env python3
"""
批量分析脚本 - 植物根长度分析

对多个数据文件执行批量分析并生成汇总报告。

使用方法:
    python batch_analysis.py --input-dir <目录路径>
    python batch_analysis.py --files file1.csv file2.csv file3.csv

输出:
    - 每个文件的独立分析结果
    - 汇总报告（summary_report.html）
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import shutil

try:
    import pandas as pd
except ImportError:
    print("错误：需要pandas包。安装: pip install pandas")
    sys.exit(1)


class BatchAnalyzer:
    """批量根长度分析器"""

    def __init__(self, skill_dir, output_base_dir="batch_results"):
        """
        初始化批量分析器

        Args:
            skill_dir: root-analysis技能目录路径
            output_base_dir: 批量结果输出目录
        """
        self.skill_dir = Path(skill_dir)
        self.validate_script = self.skill_dir / "scripts" / "validate_data.py"
        self.generate_script = self.skill_dir / "scripts" / "generate_r_project.py"
        self.output_base = Path(output_base_dir)
        self.results = []

    def find_data_files(self, input_dir):
        """
        在目录中查找数据文件

        Args:
            input_dir: 输入目录路径

        Returns:
            list: 数据文件路径列表
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"目录不存在: {input_dir}")

        # 查找CSV和Excel文件
        data_files = []
        for pattern in ['*.csv', '*.xlsx', '*.xls']:
            data_files.extend(input_path.glob(pattern))

        return sorted(data_files)

    def validate_file(self, data_file):
        """
        验证单个数据文件

        Args:
            data_file: 数据文件路径

        Returns:
            dict: 验证结果
        """
        cmd = ["python", str(self.validate_script), str(data_file)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

            validation_result = json.loads(result.stdout)
            return validation_result

        except Exception as e:
            return {
                "valid": False,
                "errors": [f"验证失败: {str(e)}"],
                "warnings": [],
                "summary": {}
            }

    def analyze_file(self, data_file, config):
        """
        分析单个文件

        Args:
            data_file: 数据文件路径
            config: 分析配置字典

        Returns:
            dict: 分析结果
        """
        file_name = data_file.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"{file_name}_{timestamp}"
        project_dir = self.output_base / project_name

        # 构建命令
        cmd = [
            "python",
            str(self.generate_script),
            "--data-file", str(data_file),
            "--color-scheme", config.get('color_scheme', 'high_contrast'),
            "--baseline-treatment", config.get('baseline_treatment', 'Mock'),
            "--project-dir", str(project_dir)
        ]

        # 添加Python模式参数
        if config.get('use_python', False):
            cmd.append("--use-python")

        # 添加可选参数
        if config.get('sample_order'):
            cmd.extend(["--sample-order", config['sample_order']])

        if config.get('width'):
            cmd.extend(["--width", str(config['width'])])

        if config.get('height'):
            cmd.extend(["--height", str(config['height'])])

        # 生成项目
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

            # 尝试解析JSON输出
            try:
                # 找到第一个'{'，然后解析到文件末尾的多行JSON
                stdout = result.stdout.strip()
                json_start = stdout.find('{')
                if json_start == -1:
                    raise ValueError(f"未找到JSON对象: {stdout}")

                json_str = stdout[json_start:]
                generation_result = json.loads(json_str)
            except (json.JSONDecodeError, ValueError) as e:
                return {
                    'file': str(data_file),
                    'status': 'failed',
                    'error': f"JSON解析错误: {str(e)}\nStdout: {result.stdout}\nStderr: {result.stderr}",
                    'project_dir': None
                }

            if not generation_result.get('success'):
                return {
                    'file': str(data_file),
                    'status': 'failed',
                    'error': generation_result.get('error', '未知错误'),
                    'project_dir': None
                }

            # 运行分析（如果配置了）
            analysis_success = True
            analysis_output = ""

            if config.get('run_analysis', True):
                use_python = config.get('use_python', False)
                analysis_success, analysis_output = self._run_analysis(
                    project_dir, use_python=use_python
                )

            return {
                'file': str(data_file),
                'status': 'success' if analysis_success else 'analysis_failed',
                'project_dir': str(project_dir),
                'analysis_output': analysis_output if not analysis_success else None,
                'mode': 'Python' if config.get('use_python', False) else 'R'
            }

        except Exception as e:
            import traceback
            return {
                'file': str(data_file),
                'status': 'failed',
                'error': f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}",
                'project_dir': None
            }

    def _run_analysis(self, project_dir, use_python=False):
        """
        运行分析（R或Python）

        Args:
            project_dir: 项目目录（Path对象或字符串）
            use_python: 是否使用Python模式

        Returns:
            tuple: (success: bool, output: str)
        """
        # 确保project_dir是Path对象
        project_dir = Path(project_dir).resolve()

        if use_python:
            # Python模式
            main_py = project_dir / "main.py"
            if not main_py.exists():
                return False, f"main.py文件不存在: {main_py}"

            try:
                result = subprocess.run(
                    ["python", "main.py"],  # 使用相对路径，因为cwd已经设置了
                    cwd=str(project_dir),
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5分钟超时
                    check=False
                )

                if result.returncode != 0:
                    return False, result.stderr

                return True, result.stdout

            except subprocess.TimeoutExpired:
                return False, "Python分析超时（>5分钟）"
            except FileNotFoundError:
                return False, "未找到Python。请确保已安装Python并添加到PATH"
            except Exception as e:
                return False, f"Python执行错误: {str(e)}"
        else:
            # R模式
            main_r = project_dir / "main.R"
            if not main_r.exists():
                return False, f"main.R文件不存在: {main_r}"

            try:
                result = subprocess.run(
                    ["Rscript", "main.R"],  # 使用相对路径，因为cwd已经设置了
                    cwd=str(project_dir),
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5分钟超时
                    check=False
                )

                if result.returncode != 0:
                    return False, result.stderr

                return True, result.stdout

            except subprocess.TimeoutExpired:
                return False, "R分析超时（>5分钟）"
            except FileNotFoundError:
                return False, "未找到Rscript。请确保已安装R并添加到PATH"
            except Exception as e:
                return False, f"R执行错误: {str(e)}"

    def batch_analyze(self, data_files, config):
        """
        批量分析多个文件

        Args:
            data_files: 数据文件列表
            config: 分析配置

        Returns:
            dict: 批量分析结果
        """
        print(f"\n开始批量分析 {len(data_files)} 个文件...\n")

        results = []
        successful = 0
        failed = 0

        for i, data_file in enumerate(data_files, 1):
            print(f"[{i}/{len(data_files)}] 分析: {data_file.name}")

            # 验证
            print("  - 验证数据格式...")
            validation = self.validate_file(data_file)

            if not validation['valid']:
                print(f"  [x] 验证失败: {validation['errors']}")
                results.append({
                    'file': str(data_file),
                    'status': 'validation_failed',
                    'validation': validation
                })
                failed += 1
                continue

            print(f"  [OK] 验证通过 ({validation['summary']['n_samples']} 样本, "
                  f"{validation['summary']['n_measurements']} 测量值)")

            # 分析
            print("  - 生成分析项目...")
            analysis_result = self.analyze_file(data_file, config)

            if analysis_result['status'] == 'success':
                print(f"  [OK] 分析完成")
                print(f"    项目目录: {analysis_result['project_dir']}")
                successful += 1
            else:
                # 获取错误信息（可能在'error'或'analysis_output'字段）
                error_msg = analysis_result.get('error') or analysis_result.get('analysis_output') or '未知错误'
                print(f"  [x] 分析失败: {error_msg}")
                failed += 1

            analysis_result['validation'] = validation
            results.append(analysis_result)
            print()

        # 生成汇总报告
        print("生成汇总报告...")
        summary = self._generate_summary(results)

        print(f"\n{'='*60}")
        print(f"批量分析完成！")
        print(f"成功: {successful} | 失败: {failed} | 总计: {len(data_files)}")
        print(f"结果保存在: {self.output_base}")
        print(f"{'='*60}\n")

        return {
            'summary': summary,
            'results': results,
            'successful': successful,
            'failed': failed,
            'total': len(data_files)
        }

    def _generate_summary(self, results):
        """
        生成HTML汇总报告

        Args:
            results: 分析结果列表

        Returns:
            str: 汇总报告路径
        """
        summary_path = self.output_base / "summary_report.html"

        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>根长度分析批量报告</title>
    <style>
        body {{
            font-family: "Microsoft YaHei", Arial, sans-serif;
            max-width: 1200px;
            margin: 40px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        .summary {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .result-card {{
            background: white;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 6px;
            border-left: 4px solid #ccc;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .success {{ border-left-color: #27ae60; }}
        .failed {{ border-left-color: #e74c3c; }}
        .warning {{ border-left-color: #f39c12; }}
        .status {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 14px;
        }}
        .status-success {{ background: #d4edda; color: #155724; }}
        .status-failed {{ background: #f8d7da; color: #721c24; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #3498db;
            color: white;
        }}
        .timestamp {{
            color: #7f8c8d;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <h1>🌱 根长度分析批量报告</h1>

    <div class="summary">
        <h2>分析概览</h2>
        <p class="timestamp">生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <table>
            <tr>
                <th>总文件数</th>
                <th>成功</th>
                <th>失败</th>
                <th>成功率</th>
            </tr>
            <tr>
                <td>{len(results)}</td>
                <td style="color: #27ae60;">{sum(1 for r in results if r['status'] == 'success')}</td>
                <td style="color: #e74c3c;">{sum(1 for r in results if r['status'] != 'success')}</td>
                <td>{sum(1 for r in results if r['status'] == 'success') / len(results) * 100:.1f}%</td>
            </tr>
        </table>
    </div>

    <h2>详细结果</h2>
"""

        for i, result in enumerate(results, 1):
            file_name = Path(result['file']).name
            status = result['status']

            status_class = 'success' if status == 'success' else 'failed'
            status_text = '✓ 成功' if status == 'success' else '✗ 失败'
            status_badge = 'status-success' if status == 'success' else 'status-failed'

            html_content += f"""
    <div class="result-card {status_class}">
        <h3>{i}. {file_name} <span class="status {status_badge}">{status_text}</span></h3>
"""

            if 'validation' in result and result['validation']['valid']:
                summary = result['validation']['summary']
                html_content += f"""
        <p><strong>数据信息:</strong> {summary['n_samples']} 样本,
           {summary['n_measurements']} 测量值,
           处理组: {', '.join(summary.get('treatments', []))}</p>
"""

            if status == 'success' and result.get('project_dir'):
                html_content += f"""
        <p><strong>项目目录:</strong> <code>{result['project_dir']}</code></p>
        <p><strong>图表:</strong>
           <a href="{Path(result['project_dir']) / 'output/figures/root_length_plot.pdf'}" target="_blank">根长度图</a> |
           <a href="{Path(result['project_dir']) / 'output/figures/ratio_plot.pdf'}" target="_blank">比率图</a>
        </p>
"""
            elif 'error' in result:
                html_content += f"""
        <p style="color: #e74c3c;"><strong>错误:</strong> {result['error']}</p>
"""

            html_content += """
    </div>
"""

        html_content += """
</body>
</html>
"""

        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return str(summary_path)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="批量分析多个根长度数据文件"
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-dir",
        help="包含数据文件的目录"
    )
    input_group.add_argument(
        "--files",
        nargs='+',
        help="要分析的数据文件列表（空格分隔）"
    )

    parser.add_argument(
        "--output-dir",
        default="batch_results",
        help="批量结果输出目录（默认: batch_results）"
    )

    parser.add_argument(
        "--color-scheme",
        choices=['default', 'high_contrast', 'blue', 'green', 'qualitative'],
        default='high_contrast',
        help="颜色方案（默认: high_contrast）"
    )

    parser.add_argument(
        "--baseline-treatment",
        default="Mock",
        help="基线处理组（默认: Mock）"
    )

    parser.add_argument(
        "--skip-analysis",
        action='store_true',
        help="跳过分析执行，仅生成项目"
    )

    parser.add_argument(
        "--use-python",
        action='store_true',
        help="使用Python模式进行分析（默认: R模式）"
    )

    parser.add_argument(
        "--skill-dir",
        help="root-analysis技能目录路径（默认: 自动检测）"
    )

    args = parser.parse_args()

    # 自动检测skill目录
    if args.skill_dir:
        skill_dir = Path(args.skill_dir)
    else:
        script_path = Path(__file__).resolve()
        skill_dir = script_path.parent.parent

    # 创建批量分析器
    analyzer = BatchAnalyzer(skill_dir, args.output_dir)

    # 获取数据文件列表
    if args.input_dir:
        try:
            data_files = analyzer.find_data_files(args.input_dir)
            if not data_files:
                print(f"错误：在 {args.input_dir} 中未找到数据文件")
                sys.exit(1)
        except FileNotFoundError as e:
            print(f"错误：{e}")
            sys.exit(1)
    else:
        data_files = [Path(f) for f in args.files]
        # 检查文件是否存在
        for f in data_files:
            if not f.exists():
                print(f"错误：文件不存在: {f}")
                sys.exit(1)

    # 配置
    config = {
        'color_scheme': args.color_scheme,
        'baseline_treatment': args.baseline_treatment,
        'run_analysis': not args.skip_analysis,
        'use_python': args.use_python
    }

    # 执行批量分析
    result = analyzer.batch_analyze(data_files, config)

    # 输出JSON结果
    output = {
        'success': result['failed'] == 0,
        'summary_report': result['summary'],
        'statistics': {
            'total': result['total'],
            'successful': result['successful'],
            'failed': result['failed']
        }
    }

    print("\nJSON输出:")
    print(json.dumps(output, indent=2, ensure_ascii=False))

    sys.exit(0 if result['failed'] == 0 else 1)


if __name__ == "__main__":
    main()
