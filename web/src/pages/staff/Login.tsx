import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { homeFor, useMe } from "../../api/auth";
import { post } from "../../api/client";
import type { UserOut } from "../../api/types";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import { ErrorBox } from "../../ui/ErrorBox";
import { Field, Fieldset } from "../../ui/Fieldset";

/** Staff Login: User ID + password. Citizens never log in. Accounts are created by the Corporation; there is no self-registration. */
export function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    document.title = `${t("login.title")} | ${t("header.nameEn")}`;
  }, [t]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await post<UserOut>("/auth/login", { username: username.trim(), password });
      navigate(homeFor(user.role), { replace: true });
    } catch (err) {
      setPassword("");
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

      {me && me.role !== "CITIZEN" ? (
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
        <form onSubmit={(e) => void submit(e)}>
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
            <Field label={t("login.password")} htmlFor="password" required wide>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
          </Fieldset>
          <button type="submit" className="btn" disabled={busy || !username.trim() || !password}>
            {t("login.submit")}
          </button>
        </form>
        <p className="muted" style={{ marginTop: 12 }}>
          {t("login.accountsNote")}
        </p>
      </div>
    </>
  );
}
