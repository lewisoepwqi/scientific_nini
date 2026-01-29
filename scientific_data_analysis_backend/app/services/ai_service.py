"""
AI Service for intelligent analysis assistance.
This is a placeholder for future AI integration.
"""
from typing import Dict, Any, List, Optional

from app.core.config import settings


class AIService:
    """
    Service for AI-powered analysis assistance.
    
    This service provides intelligent recommendations for:
    - Chart type selection
    - Statistical test selection
    - Data interpretation
    - Method suggestions
    
    Future integrations:
    - OpenAI GPT-4 for natural language analysis
    - Custom ML models for data pattern recognition
    """
    
    def __init__(self):
        self.enabled = settings.OPENAI_API_KEY is not None
        self.model = settings.OPENAI_MODEL if self.enabled else None
    
    def suggest_chart_type(
        self,
        data_summary: Dict[str, Any],
        columns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Suggest appropriate chart types based on data characteristics.
        
        Args:
            data_summary: Summary statistics of the dataset
            columns: List of column names being considered
            
        Returns:
            List of suggested chart types with confidence scores
        """
        suggestions = []
        
        # Analyze column types
        numeric_cols = data_summary.get("numeric_columns", [])
        categorical_cols = data_summary.get("categorical_columns", [])
        
        # Two numeric columns: scatter plot
        if len(numeric_cols) >= 2:
            suggestions.append({
                "chart_type": "scatter",
                "confidence": 0.9,
                "reason": "Good for showing relationship between two continuous variables",
                "requires": numeric_cols[:2]
            })
        
        # One numeric, one categorical: box/violin plot
        if len(numeric_cols) >= 1 and len(categorical_cols) >= 1:
            suggestions.append({
                "chart_type": "box",
                "confidence": 0.85,
                "reason": "Good for comparing distributions across groups",
                "requires": [numeric_cols[0], categorical_cols[0]]
            })
            suggestions.append({
                "chart_type": "violin",
                "confidence": 0.8,
                "reason": "Shows full distribution shape",
                "requires": [numeric_cols[0], categorical_cols[0]]
            })
        
        # Multiple numeric columns: heatmap
        if len(numeric_cols) >= 3:
            suggestions.append({
                "chart_type": "heatmap",
                "confidence": 0.75,
                "reason": "Good for showing correlations between multiple variables",
                "requires": numeric_cols
            })
        
        # Paired data: paired plot
        if len(categorical_cols) >= 1 and "subject" in str(categorical_cols).lower():
            suggestions.append({
                "chart_type": "paired",
                "confidence": 0.8,
                "reason": "Good for before/after or paired comparisons",
                "requires": columns
            })
        
        return sorted(suggestions, key=lambda x: x["confidence"], reverse=True)
    
    def suggest_statistical_test(
        self,
        data_summary: Dict[str, Any],
        dependent_var: str,
        independent_vars: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Suggest appropriate statistical tests.
        
        Args:
            data_summary: Summary statistics of the dataset
            dependent_var: Dependent variable name
            independent_vars: Independent variable names
            
        Returns:
            List of suggested tests with confidence scores
        """
        suggestions = []
        
        # Get variable types
        dep_type = data_summary.get("column_types", {}).get(dependent_var, "unknown")
        indep_types = [
            data_summary.get("column_types", {}).get(var, "unknown")
            for var in independent_vars
        ]
        
        # One independent variable
        if len(independent_vars) == 1:
            indep_type = indep_types[0]
            
            if dep_type == "continuous" and indep_type == "categorical":
                # Check number of groups
                n_groups = data_summary.get("unique_counts", {}).get(independent_vars[0], 2)
                
                if n_groups == 2:
                    suggestions.append({
                        "test": "t_test",
                        "confidence": 0.9,
                        "reason": "Compare means between two groups",
                        "assumptions": ["Normality", "Equal variance"],
                        "alternatives": ["mann_whitney"]  # Non-parametric alternative
                    })
                else:
                    suggestions.append({
                        "test": "one_way_anova",
                        "confidence": 0.9,
                        "reason": f"Compare means across {n_groups} groups",
                        "assumptions": ["Normality", "Equal variance", "Independence"],
                        "alternatives": ["kruskal_wallis"]  # Non-parametric alternative
                    })
            
            elif dep_type == "continuous" and indep_type == "continuous":
                suggestions.append({
                    "test": "correlation",
                    "confidence": 0.85,
                    "reason": "Measure linear relationship between variables",
                    "assumptions": ["Linearity", "No outliers"],
                    "alternatives": ["spearman_correlation"]  # Rank-based alternative
                })
                suggestions.append({
                    "test": "regression",
                    "confidence": 0.8,
                    "reason": "Model relationship and make predictions",
                    "assumptions": ["Linearity", "Independence", "Homoscedasticity", "Normality of residuals"]
                })
        
        # Multiple independent variables
        elif len(independent_vars) > 1:
            suggestions.append({
                "test": "multiple_regression",
                "confidence": 0.85,
                "reason": "Model relationship with multiple predictors",
                "assumptions": ["Linearity", "Independence", "No multicollinearity", "Normality of residuals"]
            })
        
        return sorted(suggestions, key=lambda x: x["confidence"], reverse=True)
    
    async def interpret_results(
        self,
        analysis_type: str,
        results: Dict[str, Any]
    ) -> str:
        """
        Generate human-readable interpretation of analysis results.
        
        Args:
            analysis_type: Type of analysis performed
            results: Analysis results dictionary
            
        Returns:
            Interpretation text
        """
        # This is a simplified version
        # In the future, this could use GPT-4 for more sophisticated interpretations
        
        interpretations = []
        
        if analysis_type == "t_test":
            pvalue = results.get("pvalue", 1)
            statistic = results.get("statistic", 0)
            
            if pvalue < 0.001:
                interpretations.append(
                    f"The t-test shows a highly significant difference (t={statistic:.3f}, p<0.001)."
                )
            elif pvalue < 0.05:
                interpretations.append(
                    f"The t-test shows a significant difference (t={statistic:.3f}, p={pvalue:.3f})."
                )
            else:
                interpretations.append(
                    f"The t-test shows no significant difference (t={statistic:.3f}, p={pvalue:.3f})."
                )
            
            if "effect_size" in results:
                d = results["effect_size"]
                if abs(d) < 0.2:
                    interpretations.append("The effect size is negligible.")
                elif abs(d) < 0.5:
                    interpretations.append("The effect size is small.")
                elif abs(d) < 0.8:
                    interpretations.append("The effect size is medium.")
                else:
                    interpretations.append("The effect size is large.")
        
        elif analysis_type == "anova":
            pvalue = results.get("pvalue", 1)
            f_stat = results.get("f_statistic", 0)
            
            if pvalue < 0.05:
                interpretations.append(
                    f"ANOVA shows significant differences between groups (F={f_stat:.3f}, p={pvalue:.3f})."
                )
                if "post_hoc_results" in results and results["post_hoc_results"]:
                    interpretations.append("Post-hoc tests identified specific group differences.")
            else:
                interpretations.append(
                    f"ANOVA shows no significant differences between groups (F={f_stat:.3f}, p={pvalue:.3f})."
                )
        
        elif analysis_type == "correlation":
            method = results.get("method", "pearson")
            interpretations.append(
                f"Correlation analysis using {method} method with {results.get('sample_size', 0)} observations."
            )
        
        return " ".join(interpretations) if interpretations else "Analysis completed."
    
    async def generate_analysis_plan(
        self,
        research_question: str,
        data_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate a complete analysis plan based on research question.
        
        Args:
            research_question: Natural language research question
            data_summary: Summary of available data
            
        Returns:
            Analysis plan with recommended steps
        """
        # Placeholder for future AI-powered planning
        # This could use GPT-4 to understand the research question
        # and suggest appropriate analyses
        
        return {
            "research_question": research_question,
            "suggested_steps": [
                "Explore data with descriptive statistics",
                "Check assumptions (normality, equal variance)",
                "Select appropriate statistical test",
                "Perform analysis and interpret results",
                "Create appropriate visualizations"
            ],
            "note": "Full AI-powered planning coming in future version"
        }


# Singleton instance
ai_service = AIService()
