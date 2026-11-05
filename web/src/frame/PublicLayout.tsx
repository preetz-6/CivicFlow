import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Footer } from "./Footer";
import { Header } from "./Header";
import { NavBar } from "./NavBar";
import { Ticker } from "./Ticker";
import { TopStrip } from "./TopStrip";
import s from "./frame.module.css";

/** The public GIGW frame. Every citizen-facing page renders inside it. */
export function PublicLayout() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <>
      <TopStrip />
      <Header />
      <NavBar />
      <Ticker />
      <main id="main" tabIndex={-1} className={s.main}>
        <div className="container">
          <Outlet />
        </div>
      </main>
      <Footer />
    </>
  );
}
