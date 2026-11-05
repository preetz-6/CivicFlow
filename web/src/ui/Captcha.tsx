import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import u from "./ui.module.css";

function newPair() {
  const r = () => 1 + Math.floor(Math.random() * 9);
  return { a: r(), b: r() };
}

/**
 * Simple math CAPTCHA as on government forms. Client-side only: it reports
 * whether the answer is right through onChange, and the form blocks Submit
 * until it is. Call `resetKey` changes (e.g. after Reset) to draw a new question.
 */
export function Captcha({
  id = "captcha",
  onChange,
  resetKey = 0,
}: {
  id?: string;
  onChange: (valid: boolean) => void;
  resetKey?: number;
}) {
  const { t } = useTranslation();
  const [pair, setPair] = useState(newPair);
  const [answer, setAnswer] = useState("");

  useEffect(() => {
    setPair(newPair());
    setAnswer("");
  }, [resetKey]);

  const valid = answer.trim() !== "" && Number(answer) === pair.a + pair.b;
  const showWrong = answer.trim() !== "" && !valid;

  useEffect(() => {
    onChange(valid);
  }, [valid, onChange]);

  return (
    <div className={u.captcha}>
      <label htmlFor={id} className="required">
        {t("captcha.question", { a: pair.a, b: pair.b })}
      </label>
      <div className={u.captchaRow}>
        <span className={u.captchaBox} aria-hidden="true">
          {pair.a} + {pair.b} =
        </span>
        <input
          id={id}
          inputMode="numeric"
          autoComplete="off"
          size={4}
          value={answer}
          onChange={(e) => setAnswer(e.target.value.replace(/[^0-9]/g, "").slice(0, 2))}
          aria-invalid={showWrong}
          aria-describedby={showWrong ? `${id}-error` : undefined}
          required
        />
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            setPair(newPair());
            setAnswer("");
          }}
        >
          {t("captcha.refresh")}
        </button>
      </div>
      {showWrong ? (
        <span id={`${id}-error`} className={u.error}>
          {t("captcha.wrong")}
        </span>
      ) : null}
    </div>
  );
}
