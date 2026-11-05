import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { homeFor, useMe } from "../../api/auth";
import { get, post } from "../../api/client";
import type { DemoUser, LoginOut, UserOut } from "../../api/pending";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import { ErrorBox } from "../../ui/ErrorBox";
import { Field, Fieldset } from "../../ui/Fieldset";
import { Table } from "../../ui/Table";

const ROLE_LABEL: Record<string, string> = {
  CITIZEN: "Citizen",
  WARD_OFFICER: "Ward Officer",
  FIELD_TEAM: "Field Team",
  CONTROL_ROOM: "Control Room",
};

/** Two-step demo login: username -> OTP shown on screen (simulated SMS) -> verify. */
export function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const [username, setUsername] = useState("");
  const [otpInfo, setOtpInfo] = useState<LoginOut | null>(null);
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [demoUsers, setDemoUsers] = useState<DemoUser[]>([]);

  useEffect(() => {
    document.title = `${t("login.title")} | ${t("header.nameEn")}`;
  }, [t]);

  useEffect(() => {
    get<DemoUser[]>("/auth/demo-users")
      .then(setDemoUsers)
      .catch(() => setDemoUsers([]));
  }, []);

  async function requestOtp(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await post<LoginOut>("/auth/login", { username: username.trim() });
      setOtpInfo(res);
      setOtp("");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await post<UserOut>("/auth/verify", { username: username.trim(), otp: otp.trim() });
      navigate(homeFor(user.role), { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await post("/auth/logout").catch(() => undefined);
    window.location.reload();
  }

  return (
    <>
      <Breadcrumbs items={[{ label: t("login.title") }]} />
      <h1>{t("login.title")}</h1>

      {me ? (
        <div className="notice">
          {t("login.already", { name: me.name })}{" "}
          <span className="actions" style={{ display: "inline-flex", margin: 0 }}>
            <button type="button" className="btn" onClick={() => navigate(homeFor(me.role))}>
              {t("login.continue")}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => void logout()}>
              {t("console.logout")}
            </button>
          </span>
        </div>
      ) : null}

      <div style={{ maxWidth: 560, marginTop: 16 }}>
        <ErrorBox error={error} />
        {!otpInfo ? (
          <form onSubmit={(e) => void requestOtp(e)}>
            <Fieldset legend={t("login.legend")}>
              <Field label={t("login.username")} htmlFor="username" required wide>
                <input
                  id="username"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </Field>
            </Fieldset>
            <button type="submit" className="btn" disabled={busy || !username.trim()}>
              {t("login.getOtp")}
            </button>
          </form>
        ) : (
          <form onSubmit={(e) => void verify(e)}>
            <Fieldset legend={t("login.legendOtp")}>
              <div style={{ gridColumn: "1 / -1" }}>
                <p>{t("login.sentTo", { to: otpInfo.sent_to })}</p>
                {otpInfo.otp_demo ? (
                  <p className="notice">
                    <strong>{t("login.demoOtp")}:</strong> <span style={{ fontSize: "1.25rem" }}>{otpInfo.otp_demo}</span>{" "}
                    <span className="muted">({t("login.demoOtpNote")})</span>
                  </p>
                ) : null}
              </div>
              <Field label={t("login.otp")} htmlFor="otp" required>
                <input
                  id="otp"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 8))}
                  required
                />
              </Field>
            </Fieldset>
            <div className="actions">
              <button type="submit" className="btn" disabled={busy || !otp}>
                {t("login.verify")}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setOtpInfo(null);
                  setError(null);
                }}
              >
                {t("login.changeUser")}
              </button>
            </div>
          </form>
        )}
      </div>

      {demoUsers.length > 0 ? (
        <section className="section">
          <h2>{t("login.demoUsers")}</h2>
          <p className="muted">{t("login.demoUsersNote")}</p>
          <Table<DemoUser>
            caption={t("login.demoUsers")}
            rows={demoUsers}
            rowKey={(u) => u.username}
            pageSize={20}
            columns={[
              { key: "username", header: t("login.username") },
              { key: "name", header: "Name" },
              { key: "role", header: "Role", render: (u) => ROLE_LABEL[u.role] ?? u.role },
              { key: "designation", header: "Designation", render: (u) => u.designation ?? "-" },
              { key: "ward_id", header: "Ward", render: (u) => u.ward_id ?? "-" },
              {
                key: "use",
                header: "",
                csv: () => "",
                render: (u) => (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      setUsername(u.username);
                      setOtpInfo(null);
                      document.getElementById("username")?.focus();
                    }}
                  >
                    {t("login.use")}
                  </button>
                ),
              },
            ]}
          />
        </section>
      ) : null}
    </>
  );
}
