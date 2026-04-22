import { Link } from "react-router-dom";
import { useDocumentTitle } from "../utils/useDocumentTitle";

export default function NotFoundPage() {
  useDocumentTitle("Not found · Vellum");
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="max-w-prose p-12 font-serif">
        <h1 className="text-2xl text-ink">That page isn't in the dossier.</h1>
        <p className="text-ink-muted mt-4">
          It may never have been, or it may have been filed elsewhere.
        </p>
        <Link
          to="/"
          className="font-sans text-sm text-accent hover:text-accent-hover mt-8 inline-block"
        >
          Back to the shelf.
        </Link>
      </div>
    </div>
  );
}
