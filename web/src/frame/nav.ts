/**
 * Main menu, in GIGW order. An item is listed only once its page exists
 * ("every element you render must work"). "login" is the Staff Login: citizens
 * never log in, they lodge and track with the Grievance No.
 */
export interface NavItem {
  /** key under "nav." in the i18n files */
  key: string;
  to: string;
}

export const NAV: NavItem[] = [
  { key: "home", to: "/" },
  { key: "about", to: "/about" },
  { key: "lodge", to: "/lodge" },
  { key: "track", to: "/track" },
  { key: "charter", to: "/citizen-charter" },
  { key: "wards", to: "/wards" },
  { key: "faqs", to: "/faqs" },
  { key: "contact", to: "/contact" },
  { key: "login", to: "/login" },
];
