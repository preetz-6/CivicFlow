import { Route, Routes } from "react-router-dom";
import { ConsoleLayout } from "./frame/ConsoleLayout";
import { Queue } from "./pages/officer/Queue";
import { CaseDetail } from "./pages/officer/CaseDetail";
import { MyJobs } from "./pages/field/MyJobs";
import { JobDetail } from "./pages/field/JobDetail";
import { Verification } from "./pages/control/Verification";
import { ActivityLog } from "./pages/control/ActivityLog";
import { RunDetail } from "./pages/control/RunDetail";
import { Dashboard } from "./pages/control/Dashboard";
import { HazardMap } from "./pages/control/HazardMap";
import { Incidents } from "./pages/control/Incidents";
import { Operations } from "./pages/control/Operations";
import { AgencyInbox } from "./pages/agency/Inbox";
import { PublicLayout } from "./frame/PublicLayout";
import { Home } from "./pages/citizen/Home";
import { Login } from "./pages/staff/Login";
import { Lodge } from "./pages/citizen/Lodge";
import { Ack } from "./pages/citizen/Ack";
import { Track } from "./pages/citizen/Track";
import { Wards } from "./pages/citizen/Wards";
import { INFO_PAGES } from "./pages/info/content";
import { InfoPage } from "./pages/info/InfoPage";
import { NotFound } from "./pages/info/NotFound";

const OFFICER_ROLES = ["WARD_OFFICER"];
const FIELD_ROLES = ["FIELD_TEAM"];
const CONTROL_ROLES = ["CONTROL_ROOM"];
const CONTROL_MENU = [
  { to: "/control/operations", label: "Agent Operations" },
  { to: "/control", label: "Dashboard", end: true },
  { to: "/control/complaints", label: "All Complaints" },
  { to: "/control/verification", label: "Verification Queue" },
  { to: "/control/hazards", label: "Road Hazard Map" },
  { to: "/control/incidents", label: "Incidents" },
  { to: "/control/activity", label: "Agent Activity Log" },
  { to: "/control/agency", label: "Agency Liaison" },
];

export function App() {
  return (
    <Routes>
      <Route
        path="officer"
        element={
          <ConsoleLayout
            title="Ward Officer Console"
            roles={OFFICER_ROLES}
            menu={[
              { to: "/officer", label: "Complaint Queue", end: true },
              { to: "/officer/agency", label: "Agency Liaison" },
            ]}
          />
        }
      >
        <Route index element={<Queue />} />
        <Route path="complaints/:id" element={<CaseDetail />} />
        <Route
          path="activity/:id"
          element={<RunDetail backTo="/officer" backLabel="Complaint Queue" srBase="/officer/complaints" />}
        />
        <Route path="agency" element={<AgencyInbox />} />
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
            menu={CONTROL_MENU}
          />
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="complaints" element={<Queue />} />
        <Route path="complaints/:id" element={<CaseDetail />} />
        <Route path="operations" element={<Operations />} />
        <Route path="verification" element={<Verification />} />
        <Route path="hazards" element={<HazardMap />} />
        <Route path="incidents" element={<Incidents />} />
        <Route path="activity" element={<ActivityLog />} />
        <Route
          path="activity/:id"
          element={<RunDetail backTo="/control/activity" backLabel="Agent Activity Log" srBase="/control/complaints" />}
        />
        <Route path="agency" element={<AgencyInbox />} />
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
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
