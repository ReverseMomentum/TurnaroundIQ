import { useEffect } from "react";

const SITE = "FTD — Forsaken To Decay";

function setMeta(selector, attr, value) {
  const el = document.head.querySelector(selector);
  if (el) el.setAttribute(attr, value);
}

// Keeps the title and share metadata in step with the route.
export function usePageMeta({ title, description, image }) {
  useEffect(() => {
    const full = title ? `${title} — FTD` : SITE;
    document.title = full;
    setMeta('meta[property="og:title"]', "content", full);
    if (description) {
      setMeta('meta[name="description"]', "content", description);
      setMeta('meta[property="og:description"]', "content", description);
    }
    setMeta('meta[property="og:image"]', "content", image || "/og.jpg");
  }, [title, description, image]);
}
