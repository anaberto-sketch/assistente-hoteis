import { useState } from "react";
import Dashboard from "./Dashboard";
import ChatWidget from "./ChatWidget";

export default function App() {
  // Idioma unico, compartilhado. Default es: alinha com o default do
  // backend (language_for(None) -> es) e com a maioria dos paises da base.
  const [language, setLanguage] = useState("es");

  // O toggle da landing e renderizado DENTRO do dashboard (header, ao lado
  // do avatar). Nao posicionamos aqui no App para evitar flutuar por cima
  // de elementos do painel.
  return (
    <div className="dashboard-bg">
      <Dashboard language={language} onLanguageChange={setLanguage} />
      <ChatWidget language={language} onLanguageChange={setLanguage} />
    </div>
  );
}
