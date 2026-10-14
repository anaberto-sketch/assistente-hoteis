import { useEffect, useRef, useState } from "react";
import { fetchHotels, sendChat } from "./api";
import LanguageToggle from "./LanguageToggle";

// Strings de interface indexadas por idioma. Trocar o toggle troca TUDO
// (labels, placeholders, sugestoes, erros) para o proximo turno. O historico
// ja renderizado nao e modificado -- a conversa anterior fica no idioma antigo.
const COPY = {
  pt: {
    title: "Assistente de Revenue",
    subtitle: "Pergunte sobre as métricas do seu hotel",
    hotelLabel: "Hotel:",
    greeting: (hotelName) =>
      `Olá! Sou seu assistente de performance${hotelName ? ` para ${hotelName}` : ""}. Se não entender alguma métrica do painel, me pergunte.`,
    suggestions: [
      "Como está meu hotel no geral?",
      "Qual é meu principal problema?",
      "Estou mais caro que a concorrência?",
      "O que devo fazer primeiro para vender mais?",
    ],
    typing: "escrevendo…",
    placeholder: "Escreva sua pergunta…",
    send: "Enviar",
    expand: "Expandir",
    collapse: "Recolher",
    close: "Fechar",
    openChat: "Abrir chat",
    noAnswer: "(sem resposta)",
    connectionError: "Erro de conexão.",
    tokenMissing:
      "O serviço de IA não está disponível (falta a credencial do modelo).",
    confidence: "Confiança do diagnóstico:",
  },
  es: {
    title: "Asistente de Revenue",
    subtitle: "Preguntá sobre las métricas de tu hotel",
    hotelLabel: "Hotel:",
    greeting: (hotelName) =>
      `¡Hola! Soy tu asistente de performance${hotelName ? ` para ${hotelName}` : ""}. Si no entendés alguna métrica del panel, preguntame.`,
    suggestions: [
      "¿Cómo viene mi hotel en general?",
      "¿Cuál es mi principal problema?",
      "¿Estoy más caro que la competencia?",
      "¿Qué debería hacer primero para vender más?",
    ],
    typing: "escribiendo…",
    placeholder: "Escribí tu pregunta…",
    send: "Enviar",
    expand: "Expandir",
    collapse: "Contraer",
    close: "Cerrar",
    openChat: "Abrir chat",
    noAnswer: "(sin respuesta)",
    connectionError: "Error de conexión.",
    tokenMissing:
      "El servicio de IA no está disponible (falta la credencial del modelo).",
    confidence: "Confianza del diagnóstico:",
  },
};

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

export default function ChatWidget({ language, onLanguageChange }) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [hotels, setHotels] = useState([]);
  const [hotelId, setHotelId] = useState("345798"); // demo por defecto
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bodyRef = useRef(null);

  const t = COPY[language] || COPY.es;

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
      const data = await sendChat({
        question: text,
        hotelId,
        history,
        language,
      });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: data.answer || t.noAnswer,
          levers: data.levers || [],
          confidence: data.confidence,
          guardrailFlags: data.guardrail_flags || [],
        },
      ]);
    } catch (err) {
      // sendChat anexa `code` ao Error: traduz aqui para o idioma ativo.
      const msg =
        err?.code === "token_missing" ? t.tokenMissing : t.connectionError;
      setMessages((m) => [...m, { role: "error", content: msg }]);
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
            <div className="chat-header-text">
              <div className="title">{t.title}</div>
              <div className="subtitle">{t.subtitle}</div>
            </div>
            <div className="chat-header-actions">
              <LanguageToggle
                value={language}
                onChange={onLanguageChange}
                placement="chat"
              />
              {/* Toggle between corner size and full-screen. */}
              <button
                className="icon-btn"
                onClick={() => setExpanded((e) => !e)}
                aria-label={expanded ? t.collapse : t.expand}
                title={expanded ? t.collapse : t.expand}
              >
                {expanded ? <CollapseIcon /> : <ExpandIcon />}
              </button>
              <button
                className="icon-btn"
                onClick={() => setOpen(false)}
                aria-label={t.close}
              >
                ×
              </button>
            </div>
          </div>

          <div className="hotel-bar">
            <span>{t.hotelLabel}</span>
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
                {t.greeting(currentHotel?.hotel_name)}
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
                      {t.confidence} {m.confidence}
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

            {loading && <div className="typing">{t.typing}</div>}
          </div>

          {messages.length === 0 && (
            <div className="suggestions">
              {t.suggestions.map((s) => (
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
              placeholder={t.placeholder}
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()}>
              {t.send}
            </button>
          </form>
        </div>
      )}

      <button
        className="chat-fab"
        onClick={() => setOpen((o) => !o)}
        aria-label={t.openChat}
      >
        <ChatIcon />
      </button>
    </>
  );
}
