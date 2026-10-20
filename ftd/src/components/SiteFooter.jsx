import { Link } from "react-router-dom";
import Logo from "./Logo.jsx";
import { CrossStar, Star } from "./Ornaments.jsx";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer__sign">
        <p className="site-footer__statement">Forsaken<br />to decay</p>
        <div className="site-footer__mark">
          <img src="/art/hero-skull.webp" alt="" width="1200" height="1500" loading="lazy" decoding="async" />
        </div>
        <p className="site-footer__statement site-footer__statement--right">Nothing<br />lasts</p>
      </div>
      <div className="site-footer__base">
        <span className="rule__line" />
        <Logo className="site-footer__logo" title="FTD" />
        <span className="rule__line" />
      </div>
      <div className="site-footer__meta">
        <nav aria-label="Footer">
          <Link to="/shop">Shop</Link>
          <Link to="/#about">About</Link>
          <Link to="/#waitlist">Waitlist</Link>
        </nav>
        <p className="site-footer__ornaments" aria-hidden="true">
          <CrossStar height={46} />
          <Star size={18} />
        </p>
        <p>© {new Date().getFullYear()} FTD / Forsaken To Decay</p>
      </div>
    </footer>
  );
}
