import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import { FOOTER_HELP, FOOTER_POLICIES, NAV } from "../../frame/nav";

/** Built from the same lists as the menus, so it never links to a missing page. */
export function Sitemap() {
  const { t } = useTranslation();
  return (
    <>
      <Breadcrumbs items={[{ label: t("sitemap.title") }]} />
      <h1>{t("sitemap.title")}</h1>
      <h2>{t("nav.label")}</h2>
      <ul>
        {NAV.map((n) => (
          <li key={n.key}>
            <Link to={n.to}>{t(`nav.${n.key}`)}</Link>
          </li>
        ))}
      </ul>
      <h2>{t("footer.policies")}</h2>
      <ul>
        {FOOTER_POLICIES.map((n) => (
          <li key={n.key}>
            <Link to={n.to}>{t(`footer.${n.key}`)}</Link>
          </li>
        ))}
      </ul>
      <h2>{t("footer.help")}</h2>
      <ul>
        {FOOTER_HELP.filter((n) => n.to !== "/sitemap").map((n) => (
          <li key={n.key}>
            <Link to={n.to}>{t(`footer.${n.key}`)}</Link>
          </li>
        ))}
        <li>
          <Link to="/screen-reader-access">{t("strip.screenReader")}</Link>
        </li>
      </ul>
    </>
  );
}
