import Logo from "./Logo.jsx";

// The defining composition: spiked-halo skeleton with the monumental wordmark
// set across its chest, framed by two short statements.
export default function HeroArtwork() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <p className="hero__statement hero__statement--left">
        Something
        <br />
        beautiful
        <br />
        dies
        <br />
        in you.
      </p>
      <p className="hero__statement hero__statement--right">
        Clothing
        <br />
        for the
        <br />
        disillusioned.
      </p>

      <div className="hero__stage">
        <img
          className="hero__art"
          src="/art/hero-skull.webp"
          width="1200"
          height="1500"
          alt="Screen-printed illustration of a skeletal figure, skull crowned by a spiked solar halo, collarbones and ribs exposed, in burnt-orange ink on black."
          fetchPriority="high"
          decoding="async"
        />
        <h1 id="hero-title" className="hero__title">
          <Logo className="hero__logo" title="FTD" outlined distressed />
          <span className="hero__tagline">“Forsaken to decay”</span>
        </h1>
      </div>

      <p className="hero__descriptor">
        <span>Gothic streetwear</span>
        <span aria-hidden="true">/</span>
        <span>Gymwear</span>
        <span aria-hidden="true">/</span>
        <span>Limited drops</span>
      </p>
    </section>
  );
}
