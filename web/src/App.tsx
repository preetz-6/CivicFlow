import { Route, Routes } from "react-router-dom";
import { ConsoleLayout } from "./frame/ConsoleLayout";
import { Queue } from "./pages/officer/Queue";
import { CaseDetail } from "./pages/officer/CaseDetail";
import { MyJobs } from "./pages/field/MyJobs";
import { JobDetail } from "./pages/field/JobDetail";
import { Verification } from "./pages/control/Verification";
import { PublicLayout } from "./frame/PublicLayout";
import { Home } from "./pages/citizen/Home";
import { Login } from "./pages/citizen/Login";
import { Lodge } from "./pages/citizen/Lodge";
import { Ack } from "./pages/citizen/Ack";
import { Track } from "./pages/citizen/Track";
import { Wards } from "./pages/citizen/Wards";
import { INFO_PAGES } from "./pages/info/content";
import { InfoPage } from "./pages/info/InfoPage";
import { NotFound } from "./pages/info/NotFound";
import { Sitemap } from "./pages/info/Sitemap";

const OFFICER_ROLES = ["WARD_OFFICER"];
const FIELD_ROLES = ["FIELD_TEAM"];
const CONTROL_ROLES = ["CONTROL_ROOM"];

export function App() {
  return (
    <Routes>
      <Route
        path="officer"
        element={
          <ConsoleLayout
            title="Ward Officer Console"
            roles={OFFICER_ROLES}
            menu={[{ to: "/officer", label: "Complaint Queue", end: true }]}
          />
        }
      >
        <Route index element={<Queue />} />
        <Route path="complaints/:id" element={<CaseDetail />} />
      </Route>
      <Route
        path="field"
        element={
          <ConsoleLayout title="Field Team" roles={FIELD_ROLES} menu={[{ to: "/field", label: "My Jobs", end: true }]} />
        }
      >
        <Route index element={<MyJobs />} />
        <Route path="jobs/:id" element={<JobDetail />} />
      </Route>
      <Route
        path="control"
        element={
          <ConsoleLayout
            title="Control Room"
            roles={CONTROL_ROLES}
            menu={[{ to: "/control", label: "Verification Queue", end: true }]}
          />
        }
      >
        <Route index element={<Verification />} />
      </Route>
      <Route element={<PublicLayout />}>
        <Route index element={<Home />} />
        {INFO_PAGES.map((p) => (
          <Route key={p.slug} path={p.slug} element={<InfoPage page={p} />} />
        ))}
        <Route path="lodge" element={<Lodge />} />
        <Route path="ack/:no" element={<Ack />} />
        <Route path="track" element={<Track />} />
        <Route path="wards" element={<Wards />} />
        <Route path="login" element={<Login />} />
        <Route path="sitemap" element={<Sitemap />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
