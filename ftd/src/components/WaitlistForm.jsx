import { useId, useRef, useState } from "react";
import { joinWaitlist, validateEmail } from "../lib/waitlist.js";

// Email capture for drop announcements. Success is shown only after the
// server confirms the address was stored.
export default function WaitlistForm({ source = "landing", product, colour, size, compact = false, autoFocus = false }) {
  const id = useId();
  const inputRef = useRef(null);
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [state, setState] = useState("idle"); // idle | submitting | success | error
  const [error, setError] = useState(null);
  const [already, setAlready] = useState(false);
  const [touched, setTouched] = useState(false);

  const fieldError = touched ? validateEmail(email) : null;

  async function onSubmit(e) {
    e.preventDefault();
    setTouched(true);
    const invalid = validateEmail(email);
    if (invalid) {
      setError(null);
      inputRef.current?.focus();
      return;
    }
    setState("submitting");
    setError(null);
    try {
      const res = await joinWaitlist({ email, source, product, colour, size, website });
      setAlready(res.already);
      setState("success");
    } catch (err) {
      setError(err.message);
      setState("error");
    }
  }

  if (state === "success") {
    return (
      <div className={`waitlist-form waitlist-form--done ${compact ? "waitlist-form--compact" : ""}`} role="status">
        <p className="waitlist-form__done-title">{already ? "Already on the list." : "You're on the list."}</p>
        <p className="waitlist-form__done-copy">
          {product
            ? `We'll write to ${email.trim()} when Drop 01 opens${size ? ` — ${colour ? `${colour}, ` : ""}size ${size} noted` : ""}.`
            : `We'll write to ${email.trim()} before Drop 01 opens.`}
        </p>
      </div>
    );
  }

  const message = fieldError || error;
  const busy = state === "submitting";

  return (
    <form className={`waitlist-form ${compact ? "waitlist-form--compact" : ""}`} onSubmit={onSubmit} noValidate aria-busy={busy}>
      <label htmlFor={`${id}-email`} className="visually-hidden">
        Email address
      </label>
      <div className={`waitlist-form__row ${message ? "is-invalid" : ""}`}>
        <input
          ref={inputRef}
          id={`${id}-email`}
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck="false"
          placeholder="Your email address"
          value={email}
          autoFocus={autoFocus}
          onChange={(e) => {
            setEmail(e.target.value);
            if (state === "error") setState("idle");
          }}
          onBlur={() => email && setTouched(true)}
          aria-invalid={Boolean(fieldError)}
          aria-describedby={`${id}-msg`}
          disabled={busy}
          required
        />
        <button type="submit" className="waitlist-form__submit" disabled={busy}>
          <span className="visually-hidden">{busy ? "Joining the waitlist" : "Join the waitlist"}</span>
          {busy ? (
            <span className="waitlist-form__pending" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
          ) : (
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path d="M3 12h16M13 5.5 19.5 12 13 18.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
            </svg>
          )}
        </button>
      </div>
      {/* bots fill every field; people never see this one */}
      <div className="hp" aria-hidden="true">
        <label htmlFor={`${id}-website`}>Website</label>
        <input id={`${id}-website`} name="website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
      </div>
      <p id={`${id}-msg`} className={`waitlist-form__msg ${message ? "is-error" : ""}`} aria-live="polite">
        {message || "Drop announcements only. No noise."}
      </p>
    </form>
  );
}
