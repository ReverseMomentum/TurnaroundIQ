import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import Logo from "./Logo.jsx";
import { Star } from "./Ornaments.jsx";
import { DROP } from "../data/products.js";

const LINKS = [
  { to: "/shop", label: "Shop" },
  { to: "/#about", label: "About" },
];

export default function SiteHeader() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const toggleRef = useRef(null);

  useEffect(() => setOpen(false), [location.pathname, location.hash]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("menu-open");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("menu-open");
    };
  }, [open]);

  return (
    <header className="site-header">
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="site-header__bar">
        <nav className="site-header__nav site-header__nav--left" aria-label="Primary">
          {LINKS.map((l) =>
            l.to.includes("#") ? (
              <Link key={l.to} to={l.to} className="nav-link">
                {l.label}
              </Link>
            ) : (
              <NavLink key={l.to} to={l.to} className="nav-link">
                {l.label}
              </NavLink>
            ),
          )}
        </nav>

        <button
          ref={toggleRef}
          type="button"
          className="menu-toggle"
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen((v) => !v)}
        >
          <span className="menu-toggle__bars" aria-hidden="true" />
          <span className="menu-toggle__label">{open ? "Close" : "Menu"}</span>
        </button>

        <Link to="/" className="site-header__brand" aria-label="FTD, Forsaken To Decay — home">
          <Star size={30} long className="site-header__star" />
          <Logo className="site-header__logo" title="FTD" />
          <Star size={30} long className="site-header__star" />
        </Link>

        <div className="site-header__nav site-header__nav--right">
          <span className="drop-status" title={`${DROP.code}: ${DROP.statusLabel}`}>
            <span className="drop-status__dot" aria-hidden="true" />
            {DROP.code}
            <span className="visually-hidden">: {DROP.statusLabel}</span>
          </span>
          <Link to="/#waitlist" className="nav-link nav-link--accent">
            Join waitlist
          </Link>
        </div>
      </div>

      <div id="mobile-menu" className="mobile-menu" data-open={open} hidden={!open}>
        <nav aria-label="Mobile">
          <ul>
            {LINKS.map((l) => (
              <li key={l.to}>
                <Link to={l.to}>{l.label}</Link>
              </li>
            ))}
            <li>
              <Link to="/#waitlist">Join waitlist</Link>
            </li>
          </ul>
        </nav>
        <p className="mobile-menu__status">
          {DROP.code} — {DROP.statusLabel}
        </p>
      </div>
    </header>
  );
}
