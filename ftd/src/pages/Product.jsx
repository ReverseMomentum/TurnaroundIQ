import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import ColourSelector from "../components/ColourSelector.jsx";
import ProductCard from "../components/ProductCard.jsx";
import ProductGallery from "../components/ProductGallery.jsx";
import SizeGuide from "../components/SizeGuide.jsx";
import SizeSelector from "../components/SizeSelector.jsx";
import WaitlistForm from "../components/WaitlistForm.jsx";
import { Star } from "../components/Ornaments.jsx";
import { DROP, PRODUCTS, SIZES, formatPrice, getColour, getProduct } from "../data/products.js";
import { usePageMeta } from "../lib/usePageMeta.js";
import NotFound from "./NotFound.jsx";

// each panel is a Drop 01 back print, re-inked by scripts/art_campaign.py
const CAMPAIGN = [
  {
    src: "/art/campaign-never-enough.webp",
    alt: "Campaign artwork: the Never Enough back print in burnt-orange ink, a thorned death-metal logo under a spiked halo.",
    caption: "Never Enough",
    slug: "never-enough-zip-hoodie",
  },
  {
    src: "/art/campaign-crossbone.webp",
    alt: "Campaign artwork: the two crossbone crosses from the zip hoodie's back, in burnt-orange ink around a burst of rays.",
    caption: "Crossbone",
    slug: "crossbone-zip-hoodie",
  },
  {
    src: "/art/campaign-cross.webp",
    alt: "Campaign artwork: the single FTD cross in burnt-orange ink, haloed by thin rays.",
    caption: "Cross",
    slug: "cross-zip-hoodie",
  },
];

export default function Product() {
  const { slug } = useParams();
  const product = getProduct(slug);
  if (!product) return <NotFound />;
  return <ProductView key={product.slug} product={product} />;
}

function ProductView({ product }) {
  // the colourway lives in the URL (?colour=grey) so it can be linked and shared
  const [params, setParams] = useSearchParams();
  const colour = getColour(product, params.get("colour"));
  usePageMeta({ title: product.name, description: product.summary, image: colour.images[0].src });

  const [size, setSize] = useState(null);
  const [sizeError, setSizeError] = useState(null);
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const notifyRef = useRef(null);
  const others = PRODUCTS.filter((p) => p.slug !== product.slug);
  const released = DROP.status === "live";

  useEffect(() => {
    if (notifyOpen) notifyRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [notifyOpen]);

  function onColour(id) {
    setParams(id === product.colours[0].id ? {} : { colour: id }, { replace: true });
  }

  function onNotify() {
    if (!size) {
      setSizeError("Pick a size so we can tell you if it goes fast.");
      return;
    }
    setSizeError(null);
    setNotifyOpen(true);
  }

  return (
    <>
      <nav className="crumbs" aria-label="Breadcrumb">
        <ol>
          <li><Link to="/shop">Shop</Link></li>
          <li><Link to="/shop">{DROP.code}</Link></li>
          <li aria-current="page">{product.name}</li>
        </ol>
      </nav>

      <section className="pdp" aria-labelledby="pdp-title">
        <ProductGallery images={colour.images} name={`${product.name}, ${colour.name}`} />

        <div className="pdp__info">
          <p className="label label--accent">FTD / {DROP.code}</p>
          <h1 id="pdp-title" className="pdp__title">{product.name}</h1>
          <p className="pdp__price">
            {formatPrice(product.price)}
            <span className="pdp__price-note">Indicative price — confirmed at release</span>
          </p>

          <p className="pdp__summary">{product.summary}</p>

          <div className="pdp__details">
            <h2 className="label">Details</h2>
            <ul>
              {product.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
            <p className="pdp__flag">Illustrative spec. Final fabric and construction are confirmed at release.</p>
          </div>

          <ColourSelector colours={product.colours} value={colour.id} onChange={onColour} />

          <SizeSelector
            sizes={SIZES}
            value={size}
            onChange={(s) => {
              setSize(s);
              setSizeError(null);
            }}
            error={sizeError}
          />
          <button type="button" className="text-link pdp__guide" onClick={() => setGuideOpen(true)} aria-haspopup="dialog">
            Size guide <span aria-hidden="true">→</span>
          </button>

          <p className="pdp__status">
            <span className="drop-status__dot" aria-hidden="true" />
            {DROP.code} — {released ? "Available" : DROP.statusLabel}
          </p>

          {!notifyOpen ? (
            <button type="button" className="btn" onClick={onNotify}>
              Notify me at drop
            </button>
          ) : (
            <div ref={notifyRef} className="pdp__notify">
              <p className="label">
                Notify me — {product.name}, {colour.name}, size {size}
              </p>
              <WaitlistForm source="product" product={product.slug} colour={colour.id} size={size} compact autoFocus />
              <button type="button" className="text-link" onClick={() => setNotifyOpen(false)}>
                Change colour or size
              </button>
            </div>
          )}
          <p className="pdp__fine">No checkout yet. Drop 01 opens to the waitlist first.</p>
        </div>
      </section>

      <SizeGuide open={guideOpen} onClose={() => setGuideOpen(false)} guide={product.sizeGuide} fit={product.fit} />

      <section className="campaign" aria-label="Campaign">
        {CAMPAIGN.map((c, i) => (
          <figure key={c.src} className={`campaign__item campaign__item--${i + 1}`}>
            <img src={c.src} alt={c.alt} width="900" height="1200" loading="lazy" decoding="async" />
            <figcaption>
              <span>{String(i + 1).padStart(2, "0")}</span>
              {c.slug === product.slug ? c.caption : <Link to={`/shop/${c.slug}`}>{c.caption}</Link>}
            </figcaption>
          </figure>
        ))}
      </section>

      <section className="others" aria-labelledby="others-title">
        <h2 id="others-title" className="section-title">
          <Star size={34} long />
          <span>Other pieces</span>
          <Star size={34} long />
        </h2>
        <div className="others__grid">
          {others.map((p) => (
            <ProductCard key={p.slug} product={p} index={PRODUCTS.indexOf(p)} />
          ))}
        </div>
      </section>
    </>
  );
}
