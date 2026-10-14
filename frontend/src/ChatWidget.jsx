import { useEffect, useRef, useState } from "react";
import { fetchHotels, sendChat } from "./api";

const SUGGESTIONS = [
  "¿Cómo viene mi hotel en general?",
  "¿Cuál es mi principal problema?",
  "¿Estoy más caro que la competencia?",
  "¿Qué debería hacer primero para vender más?",
];

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path
        d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ExpandIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path
        d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CollapseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path
        d="M9 3v6H3M21 15h-6v6M15 9l6-6M3 21l6-6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Lever({ lever }) {
  return (
    <div className={`lever ${lever.severity}`}>
      <div className="lever-id">{lever.id}</div>
      <div className="lever-badge">
        {lever.block} · {lever.severity}
      </div>
    </div>
  );
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [hotels, setHotels] = useState([]);
  const [hotelId, setHotelId] = useState("345798"); // demo por defecto
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    fetchHotels()
      .then((list) => {
        setHotels(list);
        if (list.length && !list.find((h) => h.hotel_id === hotelId)) {
          setHotelId(list[0].hotel_id);
        }
      })
      .catch(() => setHotels([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When docked (open + expanded) the dashboard must shrink to make room for
  // the side panel. We toggle a body class so the layout reacts to it without
  // threading state through App.
  useEffect(() => {
    const docked = open && expanded;
    document.body.classList.toggle("chat-docked", docked);
    return () => document.body.classList.remove("chat-docked");
  }, [open, expanded]);

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Al cambiar de hotel, reiniciamos la conversación (el history es por hotel).
  function onChangeHotel(e) {
    setHotelId(e.target.value);
    setMessages([]);
  }

  async function ask(question) {
    const text = question.trim();
    if (!text || loading) return;

    const userMsg = { role: "user", content: text };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    // history solo con los turnos de texto (role/content), como espera la API.
    const history = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const data = await sendChat({ question: text, hotelId, history });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: data.answer || "(sin respuesta)",
          levers: data.levers || [],
          confidence: data.confidence,
          guardrailFlags: data.guardrail_flags || [],
        },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "error", content: err.message || "Error de conexión." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  const currentHotel = hotels.find((h) => h.hotel_id === hotelId);

  return (
    <>
      {open && (
        <div className={`chat-panel ${expanded ? "expanded" : ""}`}>
          <div className="chat-header">
            <div>
              <div className="title">Asistente de Revenue</div>
              <div className="subtitle">
                Preguntá sobre las métricas de tu hotel
              </div>
            </div>
            <div className="chat-header-actions">
              {/* Toggle between corner size and full-screen. */}
              <button
                className="icon-btn"
                onClick={() => setExpanded((e) => !e)}
                aria-label={expanded ? "Contraer" : "Expandir"}
                title={expanded ? "Contraer" : "Expandir"}
              >
                {expanded ? <CollapseIcon /> : <ExpandIcon />}
              </button>
              <button
                className="icon-btn"
                onClick={() => setOpen(false)}
                aria-label="Cerrar"
              >
                ×
              </button>
            </div>
          </div>

          <div className="hotel-bar">
            <span>Hotel:</span>
            <select value={hotelId} onChange={onChangeHotel}>
              {hotels.length === 0 && <option value={hotelId}>{hotelId}</option>}
              {hotels.map((h) => (
                <option key={h.hotel_id} value={h.hotel_id}>
                  {h.hotel_name} ({h.hotel_id})
                </option>
              ))}
            </select>
          </div>

          <div className="chat-body" ref={bodyRef}>
            {messages.length === 0 && (
              <div className="msg bot">
                ¡Hola! Soy tu asistente de performance
                {currentHotel ? ` para ${currentHotel.hotel_name}` : ""}. Si no
                entendés alguna métrica del panel, preguntame.
              </div>
            )}

            {messages.map((m, i) => {
              if (m.role === "error") {
                return (
                  <div key={i} className="msg error">
                    {m.content}
                  </div>
                );
              }
              const cls = m.role === "user" ? "msg user" : "msg bot";
              return (
                <div key={i} className={cls}>
                  {m.content}
                  {m.levers && m.levers.length > 0 && (
                    <div className="levers">
                      {m.levers.map((lv, j) => (
                        <Lever key={j} lever={lv} />
                      ))}
                    </div>
                  )}
                  {m.confidence && (
                    <div className="confidence-chip">
                      Confianza del diagnóstico: {m.confidence}
                    </div>
                  )}
                  {m.guardrailFlags &&
                    m.guardrailFlags.map((f, j) => (
                      <div key={j} className="flag-note">
                        ⚠ {f}
                      </div>
                    ))}
                </div>
              );
            })}

            {loading && <div className="typing">escribiendo…</div>}
          </div>

          {messages.length === 0 && (
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}

          <form
            className="chat-footer"
            onSubmit={(e) => {
              e.preventDefault();
              ask(input);
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Escribí tu pregunta…"
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()}>
              Enviar
            </button>
          </form>
        </div>
      )}

      <button
        className="chat-fab"
        onClick={() => setOpen((o) => !o)}
        aria-label="Abrir chat"
      >
        <ChatIcon />
      </button>
    </>
  );
}
