import { Route, Routes } from "react-router-dom";
import { PublicLayout } from "./frame/PublicLayout";
import { Home } from "./pages/citizen/Home";
import { Login } from "./pages/citizen/Login";
import { Lodge } from "./pages/citizen/Lodge";
import { Ack } from "./pages/citizen/Ack";
import { Track } from "./pages/citizen/Track";
import { INFO_PAGES } from "./pages/info/content";
import { InfoPage } from "./pages/info/InfoPage";
import { NotFound } from "./pages/info/NotFound";
import { Sitemap } from "./pages/info/Sitemap";

export function App() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route index element={<Home />} />
        {INFO_PAGES.map((p) => (
          <Route key={p.slug} path={p.slug} element={<InfoPage page={p} />} />
        ))}
        <Route path="lodge" element={<Lodge />} />
        <Route path="ack/:no" element={<Ack />} />
        <Route path="track" element={<Track />} />
        <Route path="login" element={<Login />} />
        <Route path="sitemap" element={<Sitemap />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
