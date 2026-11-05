import { useEffect, useState, type ReactNode } from "react";
import { get } from "../../api/client";
import type { SlaPolicy } from "../../api/types";
import { Link } from "react-router-dom";
import { Table } from "../../ui/Table";

/**
 * Static pages linked from the nav bar, top strip and footer (About, Charter, FAQs, Contact, Accessibility, Screen Reader Access). Bodies are English only for now; titles come
 * from the i18n files where a key exists.
 */
export interface InfoPageDef {
  slug: string;
  /** i18n key for the title */
  titleKey: string;
  body: () => ReactNode;
}

function fmtHours(h: number): string {
  if (h % 24 === 0) return `${h / 24} day${h === 24 ? "" : "s"}`;
  return `${h} hour${h === 1 ? "" : "s"}`;
}

function Charter() {
  const [policies, setPolicies] = useState<SlaPolicy[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    get<SlaPolicy[]>("/public/sla-policies")
      .then(setPolicies)
      .catch(() => setFailed(true));
  }, []);
  return (
    <>
      <p>
        The Corporation commits to the following service standards for grievances lodged on this portal. Timelines
        are counted from the time the grievance is registered. They pause only for reasons
        outside the Corporation's control (waiting for another agency, weather, or information from the citizen),
        and every pause is recorded on the grievance.
      </p>
      <h2>Resolution timelines</h2>
      {failed ? <p className="notice notice-error">The timelines could not be loaded. Please try again later.</p> : null}
      {policies ? (
        <Table<SlaPolicy>
          caption="Resolution timelines"
          rows={policies}
          rowKey={(r) => `${r.category}-${r.priority}`}
          pageSize={15}
          exportName="citizen-charter-timelines"
          columns={[
            { key: "category_label", header: "Grievance type" },
            { key: "priority", header: "Priority" },
            { key: "resolution_hours", header: "Target resolution time", render: (r) => fmtHours(r.resolution_hours) },
            {
              key: "verification_hours",
              header: "Time for you to confirm",
              render: (r) => fmtHours(r.verification_hours),
            },
          ]}
        />
      ) : null}
      <p className="muted">P1 is the most urgent (danger to life or property); P4 is the least urgent.</p>
      <h2>Your rights</h2>
      <ul>
        <li>A Grievance Number and acknowledgement for every grievance.</li>
        <li>A named responsible officer and an expected resolution date.</li>
        <li>Honest updates, including the reason for any delay.</li>
        <li>Before and after photographs when work is completed.</li>
        <li>The right to reopen a grievance if the problem is not fixed.</li>
      </ul>
    </>
  );
}

export const INFO_PAGES: InfoPageDef[] = [
  {
    slug: "about",
    titleKey: "nav.about",
    body: () => (
      <>
        <p>
          CivicFlow Municipal Corporation serves Kengeri, Kengeri Satellite Town, Rajarajeshwari Nagar and
          Hemmigepura in Bengaluru West.
        </p>
        <p>
          This portal lets citizens report civic problems such as potholes, broken streetlights, garbage, water
          leaks and blocked drains, and follow each one until it is fixed. Behind the scenes, automated case
          analysis helps officers route grievances to the right ward, department or agency, chase delays, and check
          completion photographs. Officers approve every decision that affects a citizen's grievance.
        </p>
      </>
    ),
  },
  { slug: "citizen-charter", titleKey: "nav.charter", body: () => <Charter /> },
  {
    slug: "faqs",
    titleKey: "nav.faqs",
    body: () => (
      <dl>
        <dt>
          <strong>Do I need to register to lodge a grievance?</strong>
        </dt>
        <dd>No. You can lodge a grievance anonymously and track it with the tracking code on your acknowledgement.</dd>
        <dt>
          <strong>What happens if someone has already reported the same problem?</strong>
        </dt>
        <dd>
          The system links similar reports at the same location. You still receive every update on the linked
          grievance.
        </dd>
        <dt>
          <strong>Why was my grievance sent to BESCOM or BWSSB?</strong>
        </dt>
        <dd>
          Some assets, such as electricity feeders and water mains, belong to other agencies. The Corporation refers
          the grievance to them, follows up, and tells you the status.
        </dd>
        <dt>
          <strong>What if the problem is not actually fixed?</strong>
        </dt>
        <dd>When you are asked to confirm the resolution, choose Reopen and give the reason.</dd>
        <dt>
          <strong>Will I receive an SMS?</strong>
        </dt>
        <dd>
          Yes. Every update on your grievance is sent to the mobile number you give, in English or Kannada. You can
          also see every step on Track Grievance.
        </dd>
      </dl>
    ),
  },
  {
    slug: "contact",
    titleKey: "nav.contact",
    body: () => (
      <>
        <p>
          <strong>CivicFlow Municipal Corporation</strong>
          <br />
          Bengaluru West
        </p>
        <p>
          To report a civic problem, use <Link to="/lodge">Lodge Grievance</Link>. It is available 24x7 and every
          grievance gets a number you can track. Your ward officer is listed in the{" "}
          <Link to="/wards">Ward Directory</Link>.
        </p>
        <p>In an emergency where there is danger to life, call 112.</p>
      </>
    ),
  },
  {
    slug: "accessibility-statement",
    titleKey: "footer.accessibility",
    body: () => (
      <>
        <p>The portal aims to meet WCAG 2.1 level AA and the Guidelines for Indian Government Websites (GIGW).</p>
        <ul>
          <li>Text size can be changed with the A- / A / A+ buttons at the top of every page.</li>
          <li>A high-contrast mode is available from the same strip.</li>
          <li>Every page has a "Skip to main content" link and can be used with the keyboard alone.</li>
          <li>The scrolling "What's New" ticker can be paused.</li>
          <li>Citizen pages are available in English and Kannada.</li>
        </ul>
        <p>
          If you find a barrier, report it through <Link to="/lodge">Lodge Grievance</Link> (category: Other).
        </p>
      </>
    ),
  },
  {
    slug: "screen-reader-access",
    titleKey: "strip.screenReader",
    body: () => (
      <>
        <p>
          The portal follows WCAG 2.1 so that people with visual impairments can use it with screen readers such
          as the following.
        </p>
        <ul>
          <li>NVDA (Windows, free and open source)</li>
          <li>JAWS (Windows, commercial)</li>
          <li>Narrator (built into Windows)</li>
          <li>VoiceOver (built into macOS and iOS)</li>
          <li>TalkBack (built into Android)</li>
        </ul>
      </>
    ),
  },
];
