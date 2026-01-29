"""
AI服务使用示例
展示如何在Python代码中使用AI分析服务
"""
import asyncio
import os

# 设置环境变量
os.environ["OPENAI_API_KEY"] = "your_api_key_here"

from ai_service import get_ai_service, LLMConfig, ModelProvider


async def example_chart_recommendation():
    """示例：图表推荐"""
    print("=" * 50)
    print("示例1：图表推荐")
    print("=" * 50)
    
    service = get_ai_service()
    
    data_info = {
        "data_description": "包含100个样本的基因表达数据",
        "data_sample": """SampleID,GeneA,GeneB,Group
S001,2.5,3.1,Control
S002,2.8,3.5,Treatment
S003,2.3,2.9,Control
S004,3.1,3.8,Treatment
S005,2.6,3.2,Control""",
        "data_types": {
            "SampleID": "string",
            "GeneA": "float",
            "GeneB": "float",
            "Group": "categorical"
        },
        "statistics": {
            "row_count": 100,
            "column_count": 4,
            "GeneA": {"mean": 2.7, "std": 0.3},
            "GeneB": {"mean": 3.3, "std": 0.4}
        },
        "user_requirement": "比较不同组的基因表达差异"
    }
    
    try:
        result = await service.recommend_chart(
            data_description=data_info["data_description"],
            data_sample=data_info["data_sample"],
            data_types=data_info["data_types"],
            statistics=data_info["statistics"],
            user_requirement=data_info["user_requirement"]
        )
        
        print("\n主要推荐：")
        print(f"  图表类型: {result['primary_recommendation']['chart_type']}")
        print(f"  中文名: {result['primary_recommendation']['chart_name_cn']}")
        print(f"  置信度: {result['primary_recommendation']['confidence']}")
        print(f"  推荐理由: {result['primary_recommendation']['reasoning']}")
        
        print(f"\n成本: ${result.get('cost_usd', 0):.4f}")
        
    except Exception as e:
        print(f"错误: {e}")


async def example_data_analysis():
    """示例：数据分析"""
    print("\n" + "=" * 50)
    print("示例2：数据分析")
    print("=" * 50)
    
    service = get_ai_service()
    
    analysis_info = {
        "context": "研究药物X对肿瘤标志物Y的影响",
        "data_description": "随机对照试验，包含50名患者，分为对照组和治疗组",
        "statistics": {
            "control_group": {
                "n": 25,
                "mean": 45.2,
                "std": 8.3
            },
            "treatment_group": {
                "n": 25,
                "mean": 38.7,
                "std": 7.1
            },
            "t_test": {
                "t_statistic": 2.89,
                "p_value": 0.006,
                "effect_size_cohen_d": 0.82
            }
        },
        "question": "这个结果有什么统计学意义和临床意义？"
    }
    
    try:
        result = await service.analyze_data(
            context=analysis_info["context"],
            data_description=analysis_info["data_description"],
            statistics=analysis_info["statistics"],
            question=analysis_info["question"]
        )
        
        print("\n分析结果：")
        print(result["analysis"][:500] + "...")  # 只显示前500字符
        print(f"\n成本: ${result.get('cost_usd', 0):.4f}")
        print(f"Token使用: {result.get('usage', {})}")
        
    except Exception as e:
        print(f"错误: {e}")


async def example_experiment_design():
    """示例：实验设计"""
    print("\n" + "=" * 50)
    print("示例3：实验设计")
    print("=" * 50)
    
    service = get_ai_service()
    
    experiment_info = {
        "background": "研究新型抗癌药物对晚期肺癌患者的疗效",
        "objective": "评估新药物相比标准治疗在无进展生存期方面的优势",
        "study_type": "多中心随机对照试验",
        "primary_endpoint": "无进展生存期（PFS）",
        "effect_size": 0.4,  # 中效应量
        "alpha": 0.05,
        "power": 0.8,
        "test_type": "two-sided",
        "num_groups": 2,
        "additional_info": "预期脱落率15%"
    }
    
    try:
        result = await service.design_experiment(
            background=experiment_info["background"],
            objective=experiment_info["objective"],
            study_type=experiment_info["study_type"],
            primary_endpoint=experiment_info["primary_endpoint"],
            effect_size=experiment_info["effect_size"],
            alpha=experiment_info["alpha"],
            power=experiment_info["power"],
            test_type=experiment_info["test_type"],
            num_groups=experiment_info["num_groups"],
            additional_info=experiment_info["additional_info"]
        )
        
        print("\n实验设计建议：")
        print(result["design"][:500] + "...")  # 只显示前500字符
        print(f"\n成本: ${result.get('cost_usd', 0):.4f}")
        
    except Exception as e:
        print(f"错误: {e}")


async def example_streaming_analysis():
    """示例：流式数据分析"""
    print("\n" + "=" * 50)
    print("示例4：流式数据分析")
    print("=" * 50)
    
    service = get_ai_service()
    
    analysis_info = {
        "context": "单细胞RNA-seq数据分析",
        "data_description": "10000个细胞，3000个基因，分为3个细胞类型",
        "statistics": {
            "total_cells": 10000,
            "total_genes": 3000,
            "cell_types": {
                "Type_A": 3500,
                "Type_B": 3200,
                "Type_C": 3300
            },
            "qc_stats": {
                "median_genes_per_cell": 1500,
                "median_counts_per_cell": 4500
            }
        },
        "question": "这个数据质量如何？后续分析有什么建议？"
    }
    
    print("\n流式输出：")
    try:
        async for chunk in service.analyze_data_stream(
            context=analysis_info["context"],
            data_description=analysis_info["data_description"],
            statistics=analysis_info["statistics"],
            question=analysis_info["question"]
        ):
            print(chunk, end="", flush=True)
        print("\n[完成]")
        
    except Exception as e:
        print(f"\n错误: {e}")


async def example_statistical_advice():
    """示例：统计方法建议"""
    print("\n" + "=" * 50)
    print("示例5：统计方法建议")
    print("=" * 50)
    
    service = get_ai_service()
    
    advice_info = {
        "analysis_goal": "比较三个治疗组的疗效差异",
        "data_description": "随机对照试验，三组平行设计",
        "variable_info": {
            "dependent_variable": {
                "name": "疗效评分",
                "type": "continuous",
                "range": "0-100"
            },
            "independent_variable": {
                "name": "治疗组",
                "type": "categorical",
                "levels": ["A", "B", "C"]
            },
            "covariates": ["年龄", "基线评分"]
        },
        "sample_size": 150,
        "distribution_info": {
            "normality": "Shapiro-Wilk p > 0.05",
            "homoscedasticity": "Levene test p > 0.05"
        },
        "special_requirements": "需要控制混杂因素"
    }
    
    try:
        result = await service.get_statistical_advice(
            analysis_goal=advice_info["analysis_goal"],
            data_description=advice_info["data_description"],
            variable_info=advice_info["variable_info"],
            sample_size=advice_info["sample_size"],
            distribution_info=advice_info["distribution_info"],
            special_requirements=advice_info["special_requirements"]
        )
        
        print("\n统计建议：")
        print(result["advice"][:500] + "...")
        print(f"\n成本: ${result.get('cost_usd', 0):.4f}")
        
    except Exception as e:
        print(f"错误: {e}")


async def example_omics_analysis():
    """示例：多组学分析"""
    print("\n" + "=" * 50)
    print("示例6：多组学分析")
    print("=" * 50)
    
    service = get_ai_service()
    
    omics_info = {
        "omics_type": "单细胞RNA-seq",
        "data_description": "人类外周血单核细胞（PBMC）数据，使用10x Genomics平台测序",
        "sample_info": {
            "total_cells": 8000,
            "total_genes": 2000,
            "samples": ["Control_1", "Control_2", "Disease_1", "Disease_2"],
            "condition": ["Control", "Control", "Disease", "Disease"]
        },
        "analysis_goal": "识别疾病相关的细胞类型和差异表达基因",
        "completed_analysis": "已完成质控、标准化和降维",
        "specific_questions": "如何选择合适的聚类分辨率？如何进行差异分析？"
    }
    
    try:
        result = await service.analyze_omics(
            omics_type=omics_info["omics_type"],
            data_description=omics_info["data_description"],
            sample_info=omics_info["sample_info"],
            analysis_goal=omics_info["analysis_goal"],
            completed_analysis=omics_info["completed_analysis"],
            specific_questions=omics_info["specific_questions"]
        )
        
        print("\n组学分析建议：")
        print(result["analysis"][:500] + "...")
        print(f"\n成本: ${result.get('cost_usd', 0):.4f}")
        
    except Exception as e:
        print(f"错误: {e}")


async def example_cost_tracking():
    """示例：成本追踪"""
    print("\n" + "=" * 50)
    print("示例7：成本追踪")
    print("=" * 50)
    
    service = get_ai_service()
    
    # 获取成本统计
    summary = service.get_cost_summary()
    
    print("\n成本统计：")
    print(f"  总成本: ${summary['total_cost_usd']:.4f}")
    print(f"  总调用次数: {summary['total_calls']}")
    print(f"  平均每次成本: ${summary['average_cost_per_call']:.4f}")
    
    if summary['recent_calls']:
        print("\n  最近调用：")
        for i, call in enumerate(summary['recent_calls'][-3:], 1):
            print(f"    {i}. 输入: {call['input_tokens']} tokens, "
                  f"输出: {call['output_tokens']} tokens, "
                  f"成本: ${call['cost_usd']:.4f}")


async def main():
    """主函数：运行所有示例"""
    # 注意：运行这些示例需要有效的OpenAI API Key
    # 请确保已设置 OPENAI_API_KEY 环境变量
    
    if not os.getenv("OPENAI_API_KEY"):
        print("请先设置 OPENAI_API_KEY 环境变量")
        return
    
    print("AI服务使用示例")
    print("=" * 50)
    print("注意：这些示例会调用OpenAI API并产生费用")
    print("=" * 50)
    
    # 运行示例（取消注释要运行的示例）
    # await example_chart_recommendation()
    # await example_data_analysis()
    # await example_experiment_design()
    # await example_streaming_analysis()
    # await example_statistical_advice()
    # await example_omics_analysis()
    # await example_cost_tracking()
    
    print("\n" + "=" * 50)
    print("示例运行完成")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
