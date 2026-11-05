import { useLocation } from "react-router-dom";

/** "/control" or "/officer": shared staff screens link within the console they are shown in. */
export function useConsoleBase(): "/control" | "/officer" {
  return useLocation().pathname.startsWith("/control") ? "/control" : "/officer";
}
