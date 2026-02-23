/**
 * model-config 子目录共享类型定义
 */

export interface ModelPurpose {
  id: string
  label: string
}

export interface ActivePurposeModel {
  provider_id: string
  provider_name: string
  model: string
}

export interface PurposeRoute {
  provider_id: string | null
  model: string | null
  base_url: string | null
}

export interface EditForm {
  api_key: string
  model: string
  base_url: string
}

export interface TestResult {
  loading: boolean
  success?: boolean
  message?: string
}

export interface SaveStatus {
  loading: boolean
  success?: boolean
  message?: string
}

export interface RemoteModels {
  loading: boolean
  models: string[]
  source: 'remote' | 'static' | null
}

export interface ProviderOption {
  id: string
  name: string
}
