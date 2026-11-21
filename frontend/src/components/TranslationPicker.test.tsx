import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TranslationPicker } from './TranslationPicker'

afterEach(cleanup)

describe('TranslationPicker', () => {
  it('greys out languages a source does not have, with a tooltip', () => {
    const onStart = vi.fn()
    render(<TranslationPicker open track="de" available={['uz']} initial={{ lang: 'ru', direction: 'forward', remember: false }} onStart={onStart} onClose={vi.fn()} />)
    const ru = screen.getByRole('button', { name: /Русский/ }) as HTMLButtonElement
    expect(ru.disabled).toBe(true)
    expect(ru.title).toBe('Tarjima mavjud emas')
    expect((screen.getByRole('button', { name: /English/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('button', { name: /O'zbekcha/ }).getAttribute('aria-pressed')).toBe('true') // falls back to an available one
    fireEvent.click(screen.getByRole('radio', { name: /Tarjima → So'z/ }))
    fireEvent.click(screen.getByRole('button', { name: /Boshlash/ }))
    expect(onStart).toHaveBeenCalledWith({ lang: 'uz', direction: 'reverse', remember: false })
  })
})
