import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { downloadCsv, toCsv } from "./csv";
import u from "./ui.module.css";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  /** Plain value for CSV export; defaults to row[key]. */
  csv?: (row: T) => string | number | null | undefined;
  /** Right-align numbers. */
  numeric?: boolean;
}

interface CommonProps<T> {
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  caption?: string;
  /** Show the Export CSV button. Requires `exportName`. */
  exportName?: string;
  onRowClick?: (row: T) => void;
  isRowSelected?: (row: T) => boolean;
}

/** Client mode: the table holds every row and paginates locally. */
interface ClientProps<T> extends CommonProps<T> {
  rows: T[];
  pageSize?: number;
}

/**
 * Server mode: the API paginates (Page<T>). Export needs `fetchAll`, otherwise
 * the Export button is not shown (exporting one page would mislead).
 */
interface ServerProps<T> extends CommonProps<T> {
  rows: T[];
  total: number;
  page: number; // 1-based
  pageSize: number;
  onPageChange: (page: number) => void;
  fetchAll?: () => Promise<T[]>;
}

type Props<T> = ClientProps<T> | ServerProps<T>;

function isServer<T>(p: Props<T>): p is ServerProps<T> {
  return "onPageChange" in p;
}

function cellValue<T>(col: Column<T>, row: T) {
  if (col.csv) return col.csv(row);
  const v = (row as Record<string, unknown>)[col.key];
  return v === null || v === undefined ? "" : (v as string | number);
}

/**
 * Government-style table: bordered, zebra rows, navy header, S.No. column,
 * "Showing 1–10 of 245", Previous/Next, optional CSV export.
 */
export function Table<T>(props: Props<T>) {
  const { t } = useTranslation();
  const [localPage, setLocalPage] = useState(1);
  const [exporting, setExporting] = useState(false);

  const server = isServer(props);
  const pageSize = props.pageSize ?? 10;
  const total = server ? props.total : props.rows.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const page = Math.min(server ? props.page : localPage, pageCount);
  const offset = (page - 1) * pageSize;
  const visible = server ? props.rows : props.rows.slice(offset, offset + pageSize);
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + visible.length, total);

  const go = (p: number) => (server ? props.onPageChange(p) : setLocalPage(p));
  const canExport = Boolean(props.exportName) && (!server || Boolean(props.fetchAll));

  async function exportCsv() {
    setExporting(true);
    try {
      const all = server ? await props.fetchAll!() : props.rows;
      const header = [t("table.sno"), ...props.columns.map((c) => c.header)];
      const rows = all.map((r, i) => [i + 1, ...props.columns.map((c) => cellValue(c, r))]);
      downloadCsv(props.exportName!, toCsv(header, rows));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className={u.tableWrap}>
      <div className={u.tableBar}>
        <span aria-live="polite">{t("table.showing", { from, to, total })}</span>
        {canExport ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void exportCsv()}
            disabled={exporting || total === 0}
          >
            {t("table.export")}
          </button>
        ) : null}
      </div>
      <div className={u.scroll}>
        <table className={u.table}>
          {props.caption ? <caption className="visually-hidden">{props.caption}</caption> : null}
          <thead>
            <tr>
              <th scope="col" className={u.sno}>
                {t("table.sno")}
              </th>
              {props.columns.map((c) => (
                <th key={c.key} scope="col" className={c.numeric ? u.num : undefined}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={props.columns.length + 1} className={u.empty}>
                  {t("table.empty")}
                </td>
              </tr>
            ) : (
              visible.map((row, i) => {
                const selected = props.isRowSelected?.(row) ?? false;
                return (
                  <tr
                    key={props.rowKey(row)}
                    className={`${props.onRowClick ? u.clickable : ""} ${selected ? u.selected : ""}`}
                    onClick={props.onRowClick ? () => props.onRowClick!(row) : undefined}
                    aria-selected={props.onRowClick ? selected : undefined}
                  >
                    <td className={u.sno}>{offset + i + 1}</td>
                    {props.columns.map((c) => (
                      <td key={c.key} className={c.numeric ? u.num : undefined}>
                        {c.render ? c.render(row) : String(cellValue(c, row))}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {pageCount > 1 ? (
        <nav className={u.pager} aria-label={t("table.pagination")}>
          <button type="button" className="btn btn-secondary" disabled={page <= 1} onClick={() => go(page - 1)}>
            {t("table.prev")}
          </button>
          <span>
            {t("table.page", { n: page })} / {pageCount}
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={page >= pageCount}
            onClick={() => go(page + 1)}
          >
            {t("table.next")}
          </button>
        </nav>
      ) : null}
    </div>
  );
}
