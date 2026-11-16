import { useState } from 'react'

/* sending=true hone par bhi input khula rehta hai — type karte hue text dikhta hai,
   sirf Send button band hota hai jab tak Rama jawab likh raha ho. */
export default function ChatInput({ onSend, sending }) {
  const [text, setText] = useState('')

  function submit(e) {
    e.preventDefault()
    const value = text.trim()
    if (!value || sending) return
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
      />
      <button type="submit" disabled={sending || !text.trim()}>
        ➤
      </button>
    </form>
  )
}
