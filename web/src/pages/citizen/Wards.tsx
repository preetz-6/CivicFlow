import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { get } from "../../api/client";
import type { WardOut } from "../../api/types";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import { ErrorBox } from "../../ui/ErrorBox";
import { Table } from "../../ui/Table";

/** Ward Directory from GET /public/wards. */
export function Wards() {
  const { t, i18n } = useTranslation();
  const [wards, setWards] = useState<WardOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const kn = i18n.language === "kn";

  useEffect(() => {
    document.title = `${t("wards.title")} | ${t("header.nameEn")}`;
  }, [t]);

  useEffect(() => {
    get<WardOut[]>("/public/wards")
      .then(setWards)
      .catch((e) => setError(e));
  }, []);

  return (
    <>
      <Breadcrumbs items={[{ label: t("wards.title") }]} />
      <h1>{t("wards.title")}</h1>
      <ErrorBox error={error} />
      {wards ? (
        <Table<WardOut>
          caption={t("wards.title")}
          rows={wards}
          rowKey={(w) => w.id}
          exportName="ward-directory"
          columns={[
            { key: "id", header: t("wards.ward") },
            { key: "name", header: t("wards.name"), render: (w) => (kn && w.name_kn ? w.name_kn : w.name), csv: (w) => w.name },
            { key: "zone", header: t("wards.zone"), render: (w) => w.zone ?? "-" },
            { key: "officer", header: t("wards.officer"), render: (w) => w.officer?.name ?? "-", csv: (w) => w.officer?.name },
            {
              key: "designation",
              header: t("wards.designation"),
              render: (w) => w.officer?.designation ?? "-",
              csv: (w) => w.officer?.designation,
            },
          ]}
        />
      ) : null}
    </>
  );
}
