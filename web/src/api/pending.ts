/**
 * Hand-written shapes, TEMPORARY. They mirror backend/app/schemas/common.py and
 * BUILD_PLAN §10. Replace each with the generated type from schema.d.ts
 * (`npm run gen:api`) once Machine A ships the endpoint. Do not grow this file
 * beyond what the backend has not published yet.
 */

export type Role = "CITIZEN" | "WARD_OFFICER" | "FIELD_TEAM" | "CONTROL_ROOM";

/** backend/app/schemas/common.py UserOut (shipped in C1a) */
export interface UserOut {
  id: number;
  username: string;
  name: string;
  role: Role | string;
  designation?: string | null;
  ward_id?: string | null;
  zone?: string | null;
  department_id?: string | null;
  crew_id?: string | null;
  language: string;
}

/** backend/app/schemas/common.py Page[T] */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** GET /public/ticker (not shipped yet; requested in docs/REQUESTS_FOR_A.md) */
export interface TickerItem {
  id: string;
  text: string;
  published_at: string;
}
