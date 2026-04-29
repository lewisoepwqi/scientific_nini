import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import MarkdownContent from './MarkdownContent'

describe('MarkdownContent', () => {
 it('修复冒号缩写分隔行并渲染为表格', () => {
 render(
 <MarkdownContent
 content={[
 '| 项目 | 详情 |',
 '|:|:|',
 '| 数据集 | 血压心率_20220407.xlsx |',
 '| 有效样本 | n = 2,627 |',
 ].join('\n')}
 />,
 )

 expect(screen.getByRole('table')).toBeInTheDocument()
 expect(screen.getByRole('columnheader', { name: '项目' })).toBeInTheDocument()
 expect(screen.getByRole('cell', { name: '血压心率_20220407.xlsx' })).toBeInTheDocument()
 })
})
