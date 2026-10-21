// The defining composition, from the FTD concept: the spiked-halo figure with
// the FTD lettering and tagline worked into the artwork, framed by two short
// statements set as live text (scripts/art_concept.py removes them from the art).
export default function HeroArtwork() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <h1 id="hero-title" className="visually-hidden">
        FTD — Forsaken to Decay
      </h1>
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
          src="/art/hero.webp"
          width="1266"
          height="1272"
          alt="Distressed rust-red screen print of a skeletal figure crowned with a spiked halo, its decaying torso behind huge spiked FTD lettering, above the words Forsaken to Decay."
          fetchPriority="high"
          decoding="async"
        />
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
