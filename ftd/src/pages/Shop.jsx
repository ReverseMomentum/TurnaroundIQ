import { Link } from "react-router-dom";
import ProductCard from "../components/ProductCard.jsx";
import { DROP, PRODUCTS } from "../data/products.js";
import { usePageMeta } from "../lib/usePageMeta.js";

export default function Shop() {
  usePageMeta({ title: "Shop — Drop 01", description: "FTD Drop 01: the Crossbone Zip Hoodie, Crossbone Baggy Pants, Heaven Graphic Tee and Decay Tee." });
  return (
    <section className="shop" aria-labelledby="shop-title">
      <header className="shop__head">
        <p className="label label--accent">FTD / {DROP.code}</p>
        <h1 id="shop-title" className="shop__title">Drop 01</h1>
        <p className="shop__note">
          Four pieces. {DROP.statusLabel} — <Link to="/#waitlist" className="text-link">join the waitlist</Link> for first access.
        </p>
      </header>
      <div className="shop__grid">
        {PRODUCTS.map((p, i) => (
          <ProductCard key={p.slug} product={p} index={i} />
        ))}
      </div>
    </section>
  );
}
