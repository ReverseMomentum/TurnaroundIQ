import { Link } from "react-router-dom";
import { usePageMeta } from "../lib/usePageMeta.js";

export default function NotFound() {
  usePageMeta({ title: "Lost" });
  return (
    <section className="lost">
      <p className="label label--accent">404</p>
      <h1 className="lost__title">Nothing here survived.</h1>
      <Link to="/" className="text-link">Back to the start →</Link>
    </section>
  );
}
