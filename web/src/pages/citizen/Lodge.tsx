import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { post } from "../../api/client";
import { ackKey, useCategories } from "../../api/public";
import type { AckSlip } from "../../api/types";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import { Captcha } from "../../ui/Captcha";
import { ErrorBox } from "../../ui/ErrorBox";
import { Field, Fieldset } from "../../ui/Fieldset";
import { MapPicker, type LatLon } from "../../ui/MapPicker";

/** Default map centre: Kengeri (users can use their GPS position or drag the pin). */
const DEFAULT_PIN: LatLon = { lat: 12.9099, lon: 77.4855 };
const MAX_PHOTO_BYTES = 10 * 1024 * 1024;
const MOBILE_RE = /^[6-9]\d{9}$/;

export function Lodge() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const categories = useCategories();

  const [category, setCategory] = useState(params.get("category") ?? "");
  const [description, setDescription] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [pin, setPin] = useState<LatLon>(DEFAULT_PIN);
  const [landmark, setLandmark] = useState("");
  const [address, setAddress] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [declared, setDeclared] = useState(false);
  const [consented, setConsented] = useState(false);
  const [captchaOk, setCaptchaOk] = useState(false);
  const [resetKey, setResetKey] = useState(0);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    document.title = `${t("lodge.title")} | ${t("header.nameEn")}`;
  }, [t]);

  // Preview uses an object URL of the original file; nothing is re-encoded.
  useEffect(() => {
    if (!photo) {
      setPhotoPreview(null);
      return;
    }
    const url = URL.createObjectURL(photo);
    setPhotoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  const mobileInvalid = !anonymous && mobile !== "" && !MOBILE_RE.test(mobile);
  const canSubmit =
    !!category &&
    description.trim().length >= 10 &&
    (anonymous || MOBILE_RE.test(mobile)) &&
    declared &&
    consented &&
    captchaOk &&
    !busy;

  function useGps() {
    setGpsError(null);
    if (!("geolocation" in navigator)) {
      setGpsError(t("lodge.gpsFailed", { msg: "not supported" }));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setPin({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      (err) => setGpsError(t("lodge.gpsFailed", { msg: err.message })),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  function reset() {
    setCategory("");
    setDescription("");
    setPhoto(null);
    setPin(DEFAULT_PIN);
    setLandmark("");
    setAddress("");
    setAnonymous(false);
    setName("");
    setMobile("");
    setDeclared(false);
    setConsented(false);
    setError(null);
    setPhotoError(null);
    setGpsError(null);
    setResetKey((k) => k + 1);
    const input = document.getElementById("photo") as HTMLInputElement | null;
    if (input) input.value = "";
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.append("category", category);
    fd.append("description", description.trim());
    fd.append("lat", pin.lat.toFixed(6));
    fd.append("lon", pin.lon.toFixed(6));
    if (landmark.trim()) fd.append("landmark", landmark.trim());
    if (address.trim()) fd.append("address", address.trim());
    fd.append("anonymous", anonymous ? "true" : "false");
    if (!anonymous) {
      if (name.trim()) fd.append("contact_name", name.trim());
      fd.append("contact_phone", mobile);
    }
    fd.append("language", i18n.language === "kn" ? "kn" : "en");
    // The original File object, unchanged, so EXIF GPS/time reach the server.
    if (photo) fd.append("photo", photo, photo.name);
    try {
      const ack = await post<AckSlip>("/complaints", fd);
      sessionStorage.setItem(ackKey(ack.grievance_no), JSON.stringify(ack));
      navigate(`/ack/${encodeURIComponent(ack.grievance_no)}`);
    } catch (err) {
      setError(err);
      window.scrollTo(0, 0);
    } finally {
      setBusy(false);
    }
  }

  const kn = i18n.language === "kn";

  return (
    <>
      <Breadcrumbs items={[{ label: t("lodge.title") }]} />
      <h1>{t("lodge.title")}</h1>
      <p className="muted">{t("lodge.intro")}</p>
      <ErrorBox error={error} />

      <form onSubmit={(e) => void submit(e)} onReset={reset} noValidate>
        <Fieldset legend={t("lodge.grievance")}>
          <Field label={t("lodge.category")} htmlFor="category" required>
            <select id="category" value={category} onChange={(e) => setCategory(e.target.value)} required>
              <option value="">{t("lodge.select")}</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {kn ? c.label_kn : c.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("lodge.photo")} htmlFor="photo" hint={t("lodge.photoHint")} error={photoError}>
            <input
              id="photo"
              type="file"
              accept="image/jpeg,image/png"
              aria-describedby="photo-hint"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                if (f && f.size > MAX_PHOTO_BYTES) {
                  setPhotoError(t("lodge.photoTooBig"));
                  setPhoto(null);
                  e.target.value = "";
                  return;
                }
                setPhotoError(null);
                setPhoto(f);
              }}
            />
            {photoPreview ? (
              <img src={photoPreview} alt="" style={{ maxWidth: 220, maxHeight: 160, border: "1px solid var(--border)" }} />
            ) : null}
          </Field>
          <Field
            label={t("lodge.description")}
            htmlFor="description"
            required
            wide
            hint={t("lodge.descriptionHint")}
          >
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={2000}
              aria-describedby="description-hint"
              required
            />
          </Field>
        </Fieldset>

        <Fieldset legend={t("lodge.location")}>
          <div style={{ gridColumn: "1 / -1" }}>
            <p className="muted" style={{ margin: "0 0 8px" }}>
              {t("lodge.mapHint")}
            </p>
            <MapPicker value={pin} onChange={setPin} label={t("lodge.location")} />
            <div className="actions">
              <button type="button" className="btn btn-secondary" onClick={useGps}>
                {t("lodge.useGps")}
              </button>
              <span className="muted" aria-live="polite">
                {t("lodge.lat")}: {pin.lat.toFixed(6)}, {t("lodge.lon")}: {pin.lon.toFixed(6)}
              </span>
            </div>
            {gpsError ? (
              <p className="notice notice-error" role="alert" style={{ marginTop: 8 }}>
                {gpsError}
              </p>
            ) : null}
          </div>
          <Field label={t("lodge.landmark")} htmlFor="landmark">
            <input id="landmark" value={landmark} onChange={(e) => setLandmark(e.target.value)} maxLength={200} />
          </Field>
          <Field label={t("lodge.address")} htmlFor="address">
            <input id="address" value={address} onChange={(e) => setAddress(e.target.value)} maxLength={300} />
          </Field>
        </Fieldset>

        <Fieldset legend={t("lodge.contact")}>
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={{ fontWeight: 400 }}>
              <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />{" "}
              {t("lodge.anonymous")}
            </label>
          </div>
          {!anonymous ? (
            <>
              <Field label={t("lodge.name")} htmlFor="contact_name">
                <input
                  id="contact_name"
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={120}
                />
              </Field>
              <Field
                label={t("lodge.mobile")}
                htmlFor="contact_phone"
                required
                hint={t("lodge.mobileHint")}
                error={mobileInvalid ? t("lodge.mobileInvalid") : null}
              >
                <input
                  id="contact_phone"
                  inputMode="numeric"
                  autoComplete="tel-national"
                  value={mobile}
                  onChange={(e) => setMobile(e.target.value.replace(/\D/g, "").slice(0, 10))}
                  aria-invalid={mobileInvalid}
                  aria-describedby="contact_phone-hint"
                  required
                />
              </Field>
            </>
          ) : null}
        </Fieldset>

        <Fieldset legend={t("lodge.declaration")}>
          <div style={{ gridColumn: "1 / -1", display: "grid", gap: 8 }}>
            <label style={{ fontWeight: 400 }} className="required">
              <input type="checkbox" checked={declared} onChange={(e) => setDeclared(e.target.checked)} required />{" "}
              {t("lodge.declare")}
            </label>
            <label style={{ fontWeight: 400 }} className="required">
              <input type="checkbox" checked={consented} onChange={(e) => setConsented(e.target.checked)} required />{" "}
              {t("lodge.consent")}
            </label>
          </div>
          <Captcha onChange={setCaptchaOk} resetKey={resetKey} />
        </Fieldset>

        <div className="actions">
          <button type="submit" className="btn" disabled={!canSubmit}>
            {busy ? t("lodge.submitting") : t("lodge.submit")}
          </button>
          <button type="reset" className="btn btn-secondary" disabled={busy}>
            {t("lodge.reset")}
          </button>
        </div>
      </form>
    </>
  );
}
