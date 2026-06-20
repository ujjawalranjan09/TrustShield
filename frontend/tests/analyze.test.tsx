import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AnalyzePage from '@/app/[locale]/(app)/analyze/page'

vi.mock('@/lib/api', () => ({
  apiClient: {
    analyzeChat: vi.fn(),
    analyzeVoice: vi.fn(),
    analyzeImage: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = createTestQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  )
}

describe('Analyze Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the page heading', () => {
    renderWithQuery(<AnalyzePage />)
    expect(screen.getByText('Analyze')).toBeInTheDocument()
    expect(screen.getByText(/Check text messages/)).toBeInTheDocument()
  })

  it('renders tab buttons', () => {
    renderWithQuery(<AnalyzePage />)
    const buttons = screen.getAllByRole('button')
    const tabButtons = buttons.filter((b) => ['Text', 'Voice', 'Image'].some((t) => b.textContent?.trim() === t))
    expect(tabButtons).toHaveLength(3)
  })

  it('shows text tab by default', () => {
    renderWithQuery(<AnalyzePage />)
    expect(screen.getByText('Scan Text')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Paste a message/)).toBeInTheDocument()
  })

  it('renders sample message buttons', () => {
    renderWithQuery(<AnalyzePage />)
    expect(screen.getByText('OTP Scam')).toBeInTheDocument()
    expect(screen.getByText('AnyDesk Scam')).toBeInTheDocument()
    expect(screen.getByText('Legitimate')).toBeInTheDocument()
  })

  it('disables scan when textarea is empty', () => {
    renderWithQuery(<AnalyzePage />)
    expect(screen.getByText('Scan Text')).toBeDisabled()
  })

  it('calls apiClient.analyzeChat on text submission', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.analyzeChat).mockResolvedValue({
      session_id: 's1',
      risk_score: 80,
      risk_level: 'HIGH',
      recommended_action: 'BLOCK',
      flagged_entities: [],
      warning_message_en: null,
      warning_message_hi: null,
      intervention_type: 'none',
    })

    renderWithQuery(<AnalyzePage />)

    await user.type(screen.getByPlaceholderText(/Paste a message/), 'Share your OTP please')
    await user.click(screen.getByText('Scan Text'))

    expect(apiClient.analyzeChat).toHaveBeenCalled()
  })

  it('switches to voice tab', async () => {
    const user = userEvent.setup()
    renderWithQuery(<AnalyzePage />)

    await user.click(screen.getByRole('button', { name: /Voice/ }))

    expect(screen.getByText('Analyze Audio')).toBeInTheDocument()
    expect(screen.getByText(/Upload an audio file/)).toBeInTheDocument()
  })

  it('switches to image tab', async () => {
    const user = userEvent.setup()
    renderWithQuery(<AnalyzePage />)

    await user.click(screen.getByRole('button', { name: /Image/ }))

    expect(screen.getByText('Analyze Image')).toBeInTheDocument()
    expect(screen.getByText(/Upload an image/)).toBeInTheDocument()
  })

  it('loads a sample message into textarea', async () => {
    const user = userEvent.setup()
    renderWithQuery(<AnalyzePage />)

    await user.click(screen.getByText('OTP Scam'))

    const textarea = screen.getByPlaceholderText(/Paste a message/)
    expect(textarea.value).toContain('debit card block')
  })

  it('shows error on analyzeChat failure', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.analyzeChat).mockRejectedValue(new Error('Scan failed'))

    renderWithQuery(<AnalyzePage />)

    await user.type(screen.getByPlaceholderText(/Paste a message/), 'test message')
    await user.click(screen.getByText('Scan Text'))

    expect(await screen.findByText('Scan failed')).toBeInTheDocument()
  })

  it('shows verdict card on successful scan', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.analyzeChat).mockResolvedValue({
      session_id: 's1',
      risk_score: 85,
      risk_level: 'HIGH',
      recommended_action: 'BLOCK_NUMBER',
      flagged_entities: [{ entity_type: 'PHONE', value: '1234567890', start_char: 0, end_char: 10, confidence_score: 0.9 }],
      warning_message_en: null,
      warning_message_hi: null,
      intervention_type: 'none',
    })

    renderWithQuery(<AnalyzePage />)

    await user.type(screen.getByPlaceholderText(/Paste a message/), 'Call 1234567890')
    await user.click(screen.getByText('Scan Text'))

    expect(await screen.findByText('Scam Detected')).toBeInTheDocument()
    expect(screen.getByText('85')).toBeInTheDocument()
  })
})
