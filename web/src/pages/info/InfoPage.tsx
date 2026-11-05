import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import type { InfoPageDef } from "./content";

export function InfoPage({ page }: { page: InfoPageDef }) {
  const { t, i18n } = useTranslation();
  const title = t(page.titleKey);
  useEffect(() => {
    document.title = `${title} | ${t("header.nameEn")}`;
  }, [title, t]);

  return (
    <>
      <Breadcrumbs items={[{ label: title }]} />
      <h1>{title}</h1>
      {i18n.language === "kn" ? (
        <p className="notice" lang="kn">
          {t("info.englishOnly")}
        </p>
      ) : null}
      <div lang="en">{page.body()}</div>
    </>
  );
}
