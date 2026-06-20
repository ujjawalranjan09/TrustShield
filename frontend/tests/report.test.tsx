import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ReportPage from '@/app/[locale]/(public)/report/page'

vi.mock('@/lib/api', () => ({
  apiClient: {
    reportEntity: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api'

describe('Report Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the form', () => {
    render(<ReportPage />)
    expect(screen.getByText('Report Fraudulent Activity')).toBeInTheDocument()
    expect(screen.getByText('Submit Report')).toBeInTheDocument()
  })

  it('renders entity type and scam type selects', () => {
    render(<ReportPage />)
    expect(screen.getByDisplayValue('Phone Number')).toBeInTheDocument()
    expect(screen.getByDisplayValue('OTP Harvesting')).toBeInTheDocument()
  })

  it('renders the value input', () => {
    render(<ReportPage />)
    expect(screen.getByPlaceholderText('+91 98765 43210')).toBeInTheDocument()
  })

  it('disables submit when value is empty', () => {
    render(<ReportPage />)
    expect(screen.getByText('Submit Report')).toBeDisabled()
  })

  it('calls apiClient on form submission', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.reportEntity).mockResolvedValue({ report_id: 'RPT-001', status: 'success', message: 'ok' })

    render(<ReportPage />)

    const input = screen.getByPlaceholderText('+91 98765 43210')
    await user.type(input, '1234567890')

    expect(screen.getByText('Submit Report')).not.toBeDisabled()

    await user.click(screen.getByText('Submit Report'))

    expect(apiClient.reportEntity).toHaveBeenCalledWith({
      entity_value: '1234567890',
      entity_type: 'PHONE',
      scam_type: 'OTP_HARVESTING',
      description: undefined,
    })
  })

  it('shows success state after submission', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.reportEntity).mockResolvedValue({ report_id: 'RPT-001', status: 'success', message: 'ok' })

    render(<ReportPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '1234567890')
    await user.click(screen.getByText('Submit Report'))

    expect(screen.getByText('Report Submitted')).toBeInTheDocument()
    expect(screen.getByText('RPT-001')).toBeInTheDocument()
  })

  it('shows error on API failure', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.reportEntity).mockRejectedValue(new Error('Server error'))

    render(<ReportPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '1234567890')
    await user.click(screen.getByText('Submit Report'))

    expect(await screen.findByText('Server error')).toBeInTheDocument()
  })

  it('shows rate limit message on 429 error', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.reportEntity).mockRejectedValue(new Error('429 Too Many Requests'))

    render(<ReportPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '1234567890')
    await user.click(screen.getByText('Submit Report'))

    expect(await screen.findByText(/Too many reports/)).toBeInTheDocument()
  })

  it('allows reporting another after success', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.reportEntity).mockResolvedValue({ report_id: 'RPT-001', status: 'success', message: 'ok' })

    render(<ReportPage />)

    await user.type(screen.getByPlaceholderText('+91 98765 43210'), '1234567890')
    await user.click(screen.getByText('Submit Report'))

    expect(screen.getByText('Report Submitted')).toBeInTheDocument()

    await user.click(screen.getByText('Report Another'))

    expect(screen.getByText('Report Fraudulent Activity')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('+91 98765 43210')).toHaveValue('')
  })
})
