import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Breadcrumbs } from "../../frame/Breadcrumbs";

export function NotFound() {
  const { t } = useTranslation();
  return (
    <>
      <Breadcrumbs items={[{ label: t("notFound.title") }]} />
      <h1>{t("notFound.title")}</h1>
      <p>{t("notFound.body")}</p>
      <p>
        <Link to="/">{t("notFound.back")}</Link>
      </p>
    </>
  );
}
