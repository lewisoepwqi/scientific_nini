# 定义一个执行ANOVA分析的函数
perform_anova_analysis <- function(data) {
  # 使用管道操作符 %>%, 对数据按'treatment'分组并进行汇总计算
  anova_results <- data %>%
    group_by(treatment) %>%                    # 按照 'treatment' 列分组数据
    summarise(
      model = list(aov(length ~ sample,        # 对每个分组的数据应用aov()函数进行方差分析
                       data = pick(everything()))), # pick(everything())选择所有列作为模型数据
      .groups = "drop"                         # 分组操作完成后取消分组
    ) %>%
    mutate(
      anova_summary = map(model, summary),     # 对每个ANOVA模型应用summary()函数，提取统计摘要
      tukey_result = map(model, TukeyHSD),     # 对每个ANOVA模型应用TukeyHSD()函数，进行事后检验
      tukey_letters = map2(model, tukey_result, # 根据ANOVA模型和Tukey事后检验结果生成字母表示法
                           ~ multcompLetters4(.x, .y)$sample$Letters)
    )
  return(anova_results)                        # 返回包含ANOVA分析结果的数据框
}

# 定义一个处理Tukey事后检验字母标记的函数
process_tukey_letters <- function(anova_results) {
  tukey_letters_df <- anova_results %>%
    select(treatment, tukey_letters) %>%       # 选择包含处理组和Tukey字母的结果列
    rowwise() %>%                              # 将每一行视为独立组
    mutate(
      tukey_letters = list(data.frame(         # 创建一个新的data frame来存储样本名和对应的字母
        sample = names(tukey_letters),         # 提取样本名称
        letter = unlist(tukey_letters)         # 提取并展平字母列表
      ))
    ) %>%
    unnest(cols = c(tukey_letters)) %>%        # 展开嵌套的tukey_letters列到多行
    ungroup()                                  # 取消rowwise()的分组效果
  return(tukey_letters_df)                     # 返回整理后的Tukey字母标记数据框
}

# 对比率进行方差分析
analyze_ratios <- function(ratios_data) {
  # 确保数据框中包含所需的列
  if(!"ratio" %in% names(ratios_data)) {
    stop("数据中缺少 'ratio' 列")
  }
  
  if(!"sample" %in% names(ratios_data)) {
    stop("数据中缺少 'sample' 列")
  }
  
  # 进行单因素方差分析
  ratio_model <- aov(ratio ~ sample, data = ratios_data)
  
  # Tukey检验
  tukey_result <- TukeyHSD(ratio_model)
  
  # 生成显著性字母
  letters <- multcompLetters4(ratio_model, tukey_result)$sample$Letters
  
  # 创建包含字母的数据框
  letters_df <- data.frame(
    sample = names(letters),
    letter = unlist(letters)
  )
  
  return(list(
    model = ratio_model,
    tukey = tukey_result,
    letters = letters_df
  ))
}