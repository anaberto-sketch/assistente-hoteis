import { useState } from "react";
import ChatWidget from "./ChatWidget";

export default function App() {
  // Detecta si la imagen de fondo existe; si no, muestra una guía.
  const [hasBg, setHasBg] = useState(true);

  return (
    <div className="dashboard-bg">
      {/* Preload invisible: si /dashboard-bg.png no existe, mostramos la ayuda. */}
      <img
        src="/dashboard-bg.png"
        alt=""
        style={{ display: "none" }}
        onError={() => setHasBg(false)}
        onLoad={() => setHasBg(true)}
      />

      {!hasBg && (
        <div className="bg-placeholder">
          <div>
            <p>
              Poné tu captura del dashboard en{" "}
              <code>frontend/public/dashboard-bg.png</code> y recargá.
            </p>
            <p>El chat ya funciona abajo a la derecha. 👉</p>
          </div>
        </div>
      )}

      <ChatWidget />
    </div>
  );
}
