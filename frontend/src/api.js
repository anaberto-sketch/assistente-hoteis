// Cliente de la API del asistente. Un solo lugar que conoce la URL del backend.
const BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export async function fetchHotels() {
  const res = await fetch(`${BASE_URL}/hotels`);
  if (!res.ok) throw new Error(`GET /hotels falló: ${res.status}`);
  return res.json();
}

// Stateless: el cliente reenvía `history` en cada turno, como hace el CLI.
export async function sendChat({ question, hotelId, history }) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      hotel_id: hotelId || null,
      history: history || [],
    }),
  });
  if (res.status === 503) {
    // Token del LLM ausente: no es error del cliente, es indisponibilidad.
    throw new Error(
      "El servicio de IA no está disponible (falta la credencial del modelo)."
    );
  }
  if (!res.ok) throw new Error(`POST /chat falló: ${res.status}`);
  return res.json();
}
