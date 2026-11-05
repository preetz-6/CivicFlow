import { useEffect, useState, type ReactNode } from "react";
import { get } from "../../api/client";
import type { SlaPolicy } from "../../api/types";
import { Link } from "react-router-dom";
import { Table } from "../../ui/Table";

/**
 * Static pages linked from the nav bar, top strip and footer. Short and honest:
 * this is a hackathon prototype. Bodies are English only for now; titles come
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
          CivicFlow Municipal Corporation is a fictional city body created for a 24-hour hackathon. The demo area is
          Kengeri and Rajarajeshwari Nagar in Bengaluru.
        </p>
        <p>
          This portal lets citizens report civic problems such as potholes, broken streetlights, garbage, water
          leaks and blocked drains, and follow each one until it is fixed. Behind the scenes, automated case
          analysis helps officers route grievances to the right ward, department or agency, chase delays, and check
          completion photographs. Officers approve every decision that affects a citizen's grievance.
        </p>
        <p className="notice">
          This is not an official government website. All data is synthetic. Services marked (Simulated) do not
          contact any real agency.
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
        <dd>In this prototype, messages are shown on screen only (Simulated). No real SMS is sent.</dd>
      </dl>
    ),
  },
  {
    slug: "contact",
    titleKey: "nav.contact",
    body: () => (
      <>
        <p>
          <strong>CivicFlow Municipal Corporation (Demo)</strong>
          <br />
          Helpline: 1800-000-0000 (Demo number, not in service)
        </p>
        <p>
          This prototype has no real office, phone line or e-mail address. To report a civic problem in the demo,
          use Lodge Grievance on this portal.
        </p>
      </>
    ),
  },
  {
    slug: "website-policies",
    titleKey: "footer.websitePolicies",
    body: () => (
      <>
        <p>This portal is a hackathon prototype. Its policies are listed below.</p>
        <ul>
          <li>
            <Link to="/hyperlinking-policy">Hyperlinking Policy</Link>
          </li>
          <li>
            <Link to="/copyright-policy">Copyright Policy</Link>
          </li>
          <li>
            <Link to="/privacy-policy">Privacy Policy</Link>
          </li>
          <li>
            <Link to="/terms-of-use">Terms of Use</Link>
          </li>
          <li>
            <Link to="/accessibility-statement">Accessibility Statement</Link>
          </li>
        </ul>
      </>
    ),
  },
  {
    slug: "hyperlinking-policy",
    titleKey: "footer.hyperlinking",
    body: () => (
      <p>
        You may link to any page of this prototype without asking. This portal does not link to external websites,
        except the OpenStreetMap attribution shown on maps.
      </p>
    ),
  },
  {
    slug: "copyright-policy",
    titleKey: "footer.copyright",
    body: () => (
      <p>
        Content on this prototype was written for a hackathon and may be reused with attribution. The crest is an
        original drawing made for this prototype. It is not the State Emblem of India or the emblem of the
        Government of Karnataka. Map data is © OpenStreetMap contributors.
      </p>
    ),
  },
  {
    slug: "privacy-policy",
    titleKey: "footer.privacy",
    body: () => (
      <>
        <p>
          The prototype stores only what is needed to handle a grievance: the description, location, photographs
          and, if you give them, your name and mobile number. Field teams cannot see citizens' phone numbers.
        </p>
        <p>
          Connected-vehicle data (Simulated) contains only road-hazard points and a rotating anonymous vehicle
          reference. No vehicle number, rider name, phone number or trip trace is accepted.
        </p>
      </>
    ),
  },
  {
    slug: "terms-of-use",
    titleKey: "footer.terms",
    body: () => (
      <p>
        This prototype is provided for demonstration only, without any warranty. Do not use it to report real
        emergencies. For real civic grievances, contact your city corporation.
      </p>
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
        <p>If you find a barrier, tell the team presenting this prototype.</p>
      </>
    ),
  },
  {
    slug: "help",
    titleKey: "footer.helpPage",
    body: () => (
      <ul>
        <li>Use Lodge Grievance to report a problem. Keep the Grievance Number from the acknowledgement slip.</li>
        <li>Use Track Grievance with your Grievance Number and mobile number or tracking code to see progress.</li>
        <li>To change text size, contrast or language, use the controls in the dark strip at the top of every page.</li>
      </ul>
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
