import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateLead } from "../api/hooks";
import { CATEGORIES, COMPANY_SIZES } from "../api/types";
import { getReviewer, humanize } from "../lib/format";
import { Button, ErrorNote, Field, inputClass } from "./ui";

export default function NewLeadForm({ onDone }: { onDone: () => void }) {
  const create = useCreateLead();
  const navigate = useNavigate();
  const [consentEmail, setConsentEmail] = useState(true);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const text = (k: string) => (String(f.get(k) ?? "").trim() || null);
    create.mutate(
      {
        business_name: String(f.get("business_name")),
        contact_name: String(f.get("contact_name")),
        email: String(f.get("email")),
        phone: text("phone"),
        business_category: String(f.get("business_category")),
        locations_count: text("locations_count") ? Number(f.get("locations_count")) : null,
        company_size: text("company_size"),
        product_interest: (text("product_interest") ?? "").split(",").map((s) => s.trim()).filter(Boolean),
        message: text("message"),
        preferred_channel: f.get("preferred_channel") === "phone" ? "phone" : "email",
        source: "manual",
        owner: getReviewer(),
        consent: {
          email: consentEmail,
          marketing: f.get("consent_marketing") === "on",
          source_text: text("consent_source"),
        },
      },
      {
        onSuccess: (res) => {
          onDone();
          navigate(`/leads/${res.lead.id}`);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <Field label="Business name"><input name="business_name" required className={inputClass} /></Field>
      <Field label="Contact name"><input name="contact_name" required className={inputClass} /></Field>
      <Field label="Business email"><input name="email" type="email" required className={inputClass} /></Field>
      <Field label="Phone"><input name="phone" className={inputClass} /></Field>
      <Field label="Category">
        <select name="business_category" className={inputClass} defaultValue="gym">
          {CATEGORIES.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
        </select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Locations"><input name="locations_count" type="number" min={1} className={inputClass} /></Field>
        <Field label="Staff">
          <select name="company_size" className={inputClass} defaultValue="">
            <option value="">Unknown</option>
            {COMPANY_SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Product interest" hint="Comma separated, e.g. booking, memberships, payments">
        <input name="product_interest" className={inputClass} />
      </Field>
      <Field label="Preferred channel">
        <select name="preferred_channel" className={inputClass}>
          <option value="email">Email</option>
          <option value="phone">Phone</option>
        </select>
      </Field>
      <div className="sm:col-span-2">
        <Field label="Inquiry / notes from the conversation">
          <textarea name="message" rows={3} className={inputClass} />
        </Field>
      </div>
      <div className="space-y-2 text-sm sm:col-span-2">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={consentEmail} onChange={(e) => setConsentEmail(e.target.checked)} />
          Contact agreed to be emailed about their inquiry
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" name="consent_marketing" />
          Contact agreed to marketing emails
        </label>
        {consentEmail && (
          <input name="consent_source" placeholder="How was consent given? (e.g. phone call 12 May)" className={inputClass} />
        )}
      </div>
      <div className="sm:col-span-2">
        <ErrorNote error={create.error} />
        <Button type="submit" variant="primary" disabled={create.isPending}>
          {create.isPending ? "Saving…" : "Create lead"}
        </Button>
      </div>
    </form>
  );
}
