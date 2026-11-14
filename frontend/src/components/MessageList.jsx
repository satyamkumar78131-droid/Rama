export default function MessageList({ messages, typing }) {
  return (
    <div className="messages">
      {messages.length === 0 && (
        <div className="empty">
          <div className="empty-logo">🙏</div>
          <h2>Namaste! Main Rama hoon.</h2>
          <p>Kuch bhi poochho — main madad karunga. 😊</p>
          <p className="muted">Tip: "yaad rakho mera favourite colour neela hai" likh ke dekho!</p>
        </div>
      )}
      {messages.map((m, i) => (
        <div key={i} className={`msg-row ${m.role === 'user' ? 'right' : 'left'}`}>
          <div className={`bubble ${m.role === 'user' ? 'user' : 'ai'}`}>
            <div className="bubble-text">{m.content}</div>
            {m.sources && m.sources.length > 0 && (
              <div className="sources">
                {m.sources.map((s, j) => (
                  <a key={j} href={s.url} target="_blank" rel="noreferrer">
                    🔗 {s.source || s.title}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
      {typing && (
        <div className="msg-row left">
          <div className="bubble ai typing">Rama likh raha hai...</div>
        </div>
      )}
    </div>
  )
}
