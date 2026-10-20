import { Link } from "react-router-dom";
import HeroArtwork from "../components/HeroArtwork.jsx";
import WaitlistForm from "../components/WaitlistForm.jsx";
import { CrossStar, Rule, Star } from "../components/Ornaments.jsx";
import { PRODUCTS, formatPrice } from "../data/products.js";
import { usePageMeta } from "../lib/usePageMeta.js";

export default function Landing() {
  usePageMeta({
    description: "FTD — Forsaken To Decay. Gothic streetwear and gymwear in limited drops. Join the waitlist for Drop 01.",
  });
  const lead = PRODUCTS[0];

  return (
    <>
      <HeroArtwork />

      <section id="waitlist" className="waitlist" aria-labelledby="waitlist-title">
        <Star className="waitlist__star waitlist__star--l" size={64} long />
        <div className="waitlist__body">
          <h2 id="waitlist-title" className="waitlist__title">Join the waitlist</h2>
          <p className="waitlist__copy">Be first in line for Drop 01 and early access.</p>
          <WaitlistForm source="landing" />
        </div>
        <Star className="waitlist__star waitlist__star--r" size={64} long />
      </section>

      <section id="about" className="ruin" aria-labelledby="about-title">
        <div className="ruin__art">
          <CrossStar className="ruin__cross ruin__cross--l" height={220} />
          <img
            src="/art/cathedral.webp"
            width="1600"
            height="760"
            loading="lazy"
            decoding="async"
            alt="Screen-printed illustration of a ruined gothic cathedral: a rose window, a broken spire and a great arched portal above a field of rubble."
          />
          <CrossStar className="ruin__cross ruin__cross--r" height={220} />
        </div>
        <div className="ruin__text">
          <h2 id="about-title" className="label label--accent">About</h2>
          <p className="ruin__statement">
            Made in small runs for the ones who never fit the room. Printed heavy, cut loose, built to wear down
            with you — and outlast whatever you were before.
          </p>
        </div>
      </section>

      <Rule label="Drop 01" />

      <section className="preview" aria-labelledby="preview-title">
        <Link to={`/shop/${lead.slug}`} className="preview__link">
          <img src={lead.images[0].thumb} alt="" width="400" height="440" loading="lazy" decoding="async" />
          <span className="preview__text">
            <span className="label">First piece</span>
            <span id="preview-title" className="preview__name">{lead.name}</span>
            <span className="preview__price">{formatPrice(lead.price)}</span>
          </span>
          <span className="preview__cta">
            View the piece
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M3 12h16M13 5.5 19.5 12 13 18.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
            </svg>
          </span>
        </Link>
      </section>
    </>
  );
}
