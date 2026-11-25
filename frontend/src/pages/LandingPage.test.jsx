import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import LandingPage from './LandingPage.jsx'

describe('LandingPage', () => {
  it('renders landing page brand and launch app CTAs', () => {
    render(
      <BrowserRouter>
        <LandingPage />
      </BrowserRouter>
    )

    // Check brand presence
    expect(screen.getByText('MedAugment')).toBeInTheDocument()

    // Check "Launch App" button exists and points to /app
    const launchButtons = screen.getAllByRole('link', { name: /launch app/i })
    expect(launchButtons.length).toBeGreaterThanOrEqual(1)
    expect(launchButtons[0]).toHaveAttribute('href', '/app')

    // Check initial story section content
    expect(
      screen.getByText(/The Transformative Power of AI in Diagnostic Radiology/i)
    ).toBeInTheDocument()
  })
})
