import { useState } from 'react'

export default function ChatInput({ onSend, disabled }) {
  const [text, setText] = useState('')

  function submit(e) {
    e.preventDefault()
    const value = text.trim()
    if (!value || disabled) return
    onSend(value)
    setText('')
  }

  return (
    <form className="input-bar" onSubmit={submit}>
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Rama se kuch poochho..."
        disabled={disabled}
      />
      <button type="submit" disabled={disabled || !text.trim()}>
        ➤
      </button>
    </form>
  )
}
