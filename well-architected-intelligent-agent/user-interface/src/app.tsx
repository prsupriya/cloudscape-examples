import { HashRouter, BrowserRouter, Routes, Route } from "react-router-dom";
import { USE_BROWSER_ROUTER } from "./common/constants";
import GlobalHeader from "./components/global-header";
import NavigationPanel from "./components/navigation-panel";
import NotFound from "./pages/not-found";
import ChatPage from "./pages/chat/chat";
import "./styles/app.scss";

export default function App() {
  const Router = USE_BROWSER_ROUTER ? BrowserRouter : HashRouter;

  return (
    <div style={{ height: "100%" }}>
      <Router>
        <GlobalHeader />
        <div style={{ height: "56px", backgroundColor: "#000716" }}>&nbsp;</div>
        <div style={{ display: "flex", height: "calc(100vh - 56px)" }}>
          {/* Navigation Panel */}
          <div style={{ width: "280px", borderRight: "1px solid #e9eaea" }}>
            <NavigationPanel />
          </div>
          
          {/* Main Content Area */}
          <div style={{ flex: 1, overflow: "auto" }}>
            <Routes>
              <Route index path="/" element={<ChatPage />} />
              <Route index path="/assess" element={<ChatPage />} />
              <Route index path="/design" element={<ChatPage />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </div>
        </div>
      </Router>
    </div>
  );
}
