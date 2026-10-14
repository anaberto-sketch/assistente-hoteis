import Dashboard from "./Dashboard";
import ChatWidget from "./ChatWidget";

export default function App() {
  return (
    // .dashboard-bg stays as the layout wrapper so the chat side-panel can
    // shrink it (see body.chat-docked rule). It no longer renders an image.
    <div className="dashboard-bg">
      <Dashboard />
      <ChatWidget />
    </div>
  );
}
