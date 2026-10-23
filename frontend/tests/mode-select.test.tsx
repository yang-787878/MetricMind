import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ModeSelect } from '@/components/app/ModeSelect'

describe('ModeSelect', () => {
  it('渲染三种模式并标出当前选择', () => {
    render(<ModeSelect value="auto" onChange={() => {}} />)
    const radios = screen.getAllByRole('radio')
    expect(radios).toHaveLength(3)
    expect(screen.getByRole('radio', { name: /^自动：/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /^Live：/ })).toHaveAttribute('aria-checked', 'false')
  })

  it('点击切换模式', async () => {
    const onChange = vi.fn()
    render(<ModeSelect value="auto" onChange={onChange} />)
    await userEvent.click(screen.getByRole('radio', { name: /^Demo：/ }))
    expect(onChange).toHaveBeenCalledWith('demo')
  })

  it('禁用时不可切换', async () => {
    const onChange = vi.fn()
    render(<ModeSelect value="auto" onChange={onChange} disabled />)
    const live = screen.getByRole('radio', { name: /^Live：/ })
    expect(live).toBeDisabled()
    await userEvent.click(live)
    expect(onChange).not.toHaveBeenCalled()
  })
})

