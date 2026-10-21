// Client for the waitlist API (server/waitlist_api.py). Only a 2xx response with
// { ok: true } counts as a signup; anything else surfaces as an error.

const ENDPOINT = (import.meta.env.VITE_WAITLIST_ENDPOINT || "/api/waitlist").trim();

// Deliberately simple: the server is the authority, this only catches typos early.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function validateEmail(value) {
  const email = value.trim();
  if (!email) return "Enter your email address.";
  if (email.length > 254 || !EMAIL_RE.test(email)) return "That email address doesn't look right.";
  return null;
}

export async function joinWaitlist({ email, source, product, colour, size, website }) {
  let res;
  try {
    res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), source, product, colour, size, website }),
    });
  } catch {
    throw new Error("Couldn't reach the server. Check your connection and try again.");
  }
  let body = {};
  try {
    body = await res.json();
  } catch {
    // non-JSON error page from a proxy
  }
  if (!res.ok || body.ok !== true) {
    throw new Error(body.error || "Something went wrong. Your email wasn't saved. Try again shortly.");
  }
  return { already: Boolean(body.already) };
}
