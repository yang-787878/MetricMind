import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { QuestionComposer } from '@/components/app/QuestionComposer'

describe('QuestionComposer', () => {
  it('Enter 提交去除首尾空格的问题', async () => {
    const onSubmit = vi.fn()
    render(<QuestionComposer examples={['为什么 9 月销售额下降？']} onSubmit={onSubmit} />)
    const input = screen.getByLabelText('分析问题')
    await userEvent.type(input, '  为什么下降？  ')
    await userEvent.keyboard('{Enter}')
    expect(onSubmit).toHaveBeenCalledWith('为什么下降？')
  })

  it('少于 3 个字符时提示且不提交', async () => {
    const onSubmit = vi.fn()
    render(<QuestionComposer examples={['示例问题']} onSubmit={onSubmit} />)
    const input = screen.getByLabelText('分析问题')
    await userEvent.type(input, '啊')
    await userEvent.keyboard('{Enter}')
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText('请至少输入 3 个字符的问题')).toBeInTheDocument()
  })

  it('超过 500 字符时拒绝提交', async () => {
    const onSubmit = vi.fn()
    render(<QuestionComposer examples={['示例问题']} onSubmit={onSubmit} />)
    const input = screen.getByLabelText('分析问题')
    fireEvent.change(input, { target: { value: 'a'.repeat(501) } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText('问题最多 500 个字符')).toBeInTheDocument()
    expect(screen.getByText('501/500')).toBeInTheDocument()
  })

  it('禁用态不可提交', async () => {
    const onSubmit = vi.fn()
    render(
      <QuestionComposer
        examples={['示例问题']}
        onSubmit={onSubmit}
        disabled
        disabledReason="正在创建分析…"
      />,
    )
    const input = screen.getByLabelText('分析问题')
    expect(input).toBeDisabled()
    expect(screen.getByText('正在创建分析…')).toBeInTheDocument()
  })
})
