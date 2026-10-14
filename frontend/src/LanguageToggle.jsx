// Toggle PT/ES compartilhado entre a landing e o header do chat.
// placement: "landing" (fixo no canto superior direito) | "chat" (inline no header).
export default function LanguageToggle({ value, onChange, placement = "landing" }) {
  return (
    <div className={`lang-toggle lang-toggle-${placement}`} role="group" aria-label="Idioma">
      <button
        type="button"
        className={value === "pt" ? "active" : ""}
        onClick={() => onChange("pt")}
        aria-pressed={value === "pt"}
      >
        PT
      </button>
      <button
        type="button"
        className={value === "es" ? "active" : ""}
        onClick={() => onChange("es")}
        aria-pressed={value === "es"}
      >
        ES
      </button>
    </div>
  );
}
