import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import CheckPage from '@/app/[locale]/(public)/check/page'

vi.mock('@/lib/api', () => ({
  apiClient: {
    lookupEntity: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api'

describe('Check Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the form', () => {
    render(<CheckPage />)
    expect(screen.getByText('Check Reputation')).toBeInTheDocument()
    expect(screen.getByText('Check Entity')).toBeInTheDocument()
  })

  it('renders entity type select', () => {
    render(<CheckPage />)
    expect(screen.getByDisplayValue('Phone Number')).toBeInTheDocument()
  })

  it('renders the value input', () => {
    render(<CheckPage />)
    expect(screen.getByPlaceholderText('+91 98765 43210')).toBeInTheDocument()
  })

  it('disables submit when value is empty', () => {
    render(<CheckPage />)
    expect(screen.getByText('Check Entity')).toBeDisabled()
  })

  it('calls apiClient.lookupEntity on form submission', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.lookupEntity).mockResolvedValue({
      entity_value: '1234567890',
      entity_type: 'PHONE',
      is_flagged: false,
      report_count: 0,
      risk_level: 'LOW',
    })

    render(<CheckPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '1234567890')
    await user.click(screen.getByText('Check Entity'))

    expect(apiClient.lookupEntity).toHaveBeenCalledWith('PHONE', '1234567890')
  })

  it('shows result after successful lookup', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.lookupEntity).mockResolvedValue({
      entity_value: '1234567890',
      entity_type: 'PHONE',
      is_flagged: false,
      report_count: 0,
      risk_level: 'LOW',
    })

    render(<CheckPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '1234567890')
    await user.click(screen.getByText('Check Entity'))

    expect(await screen.findByText('1234567890')).toBeInTheDocument()
    expect(screen.getByText('Low Risk')).toBeInTheDocument()
    expect(screen.getByText('CLEAR')).toBeInTheDocument()
  })

  it('shows flagged state for high-risk entities', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.lookupEntity).mockResolvedValue({
      entity_value: 'scammer@upi',
      entity_type: 'UPI',
      is_flagged: true,
      report_count: 15,
      risk_level: 'HIGH',
    })

    render(<CheckPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), 'scammer@upi')
    await user.click(screen.getByText('Check Entity'))

    expect(await screen.findByText('High Risk')).toBeInTheDocument()
    expect(screen.getByText('FLAGGED')).toBeInTheDocument()
    expect(screen.getByText('15')).toBeInTheDocument()
  })

  it('shows error on API failure', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.lookupEntity).mockRejectedValue(new Error('Network error'))

    render(<CheckPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '1234567890')
    await user.click(screen.getByText('Check Entity'))

    expect(await screen.findByText('Network error')).toBeInTheDocument()
  })

  it('shows rate limit message on 429 error', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.lookupEntity).mockRejectedValue(new Error('429 rate limit'))

    render(<CheckPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '1234567890')
    await user.click(screen.getByText('Check Entity'))

    expect(await screen.findByText(/Too many requests/)).toBeInTheDocument()
  })
})
