import { Link } from "react-router-dom";
import { formatPrice } from "../data/products.js";

export default function ProductCard({ product, index }) {
  const img = product.images[0];
  return (
    <article className="card">
      <Link to={`/shop/${product.slug}`} className="card__link">
        <span className="card__index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
        <div className="card__media">
          <img src={img.src} alt={img.alt} width="1000" height="1100" loading="lazy" decoding="async" />
        </div>
        <div className="card__meta">
          <h3 className="card__name">{product.name}</h3>
          <p className="card__price">{formatPrice(product.price)}</p>
        </div>
      </Link>
    </article>
  );
}
