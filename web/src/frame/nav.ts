/**
 * Main menu, in GIGW order. An item is listed only once its page exists
 * ("every element you render must work"). Step 2 adds, in this order:
 * lodge (/lodge) after about, track (/track) after lodge, wards (/wards) after
 * charter, login (/login) at the end.
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
  { key: "faqs", to: "/faqs" },
  { key: "contact", to: "/contact" },
  { key: "login", to: "/login" },
];

/** Footer link columns. Every slug has a page in pages/info/content.ts. */
export const FOOTER_POLICIES = [
  { key: "websitePolicies", to: "/website-policies" },
  { key: "hyperlinking", to: "/hyperlinking-policy" },
  { key: "copyright", to: "/copyright-policy" },
  { key: "privacy", to: "/privacy-policy" },
  { key: "terms", to: "/terms-of-use" },
];

export const FOOTER_HELP = [
  { key: "accessibility", to: "/accessibility-statement" },
  { key: "helpPage", to: "/help" },
  { key: "sitemap", to: "/sitemap" },
];
