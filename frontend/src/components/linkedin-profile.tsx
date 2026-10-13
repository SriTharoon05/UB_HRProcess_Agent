import { useState } from "react";
import { Linkedin } from "lucide-react";
import type { LinkedInProfile } from "../lib/types";
import { contactEmail, profilePhoto } from "../lib/profile";

export function LinkedInProfileSummary({ profile }: { profile: LinkedInProfile }) {
  const [failedPhoto, setFailedPhoto] = useState<string | null>(null);
  const photo = profilePhoto(profile.picture);
  const email = contactEmail(profile.email);
  const fields = [
    ["Full name", profile.name],
    ["Given name", profile.given_name],
    ["Family name", profile.family_name],
    ["Email address", email],
    [
      "Email verification",
      typeof profile.email_verified === "boolean"
        ? profile.email_verified ? "Verified by LinkedIn" : "Not verified by LinkedIn"
        : null,
    ],
    ["Language / locale", profile.locale],
  ].filter(([, value]) => Boolean(value));
  return (
    <section className="linkedin-profile-summary" aria-labelledby="linkedin-profile-title">
      <div className="linkedin-profile-heading">
        {photo && failedPhoto !== photo ? (
          <img
            className="linkedin-profile-photo"
            src={photo}
            alt="LinkedIn profile photo"
            referrerPolicy="no-referrer"
            onError={() => setFailedPhoto(photo)}
          />
        ) : <Linkedin size={24} aria-hidden="true" />}
        <div>
          <h2 id="linkedin-profile-title">Connected with LinkedIn</h2>
          <p className="linkedin-profile-copy">
            These are the profile details LinkedIn shared with us. Confirm or add your contact details below.
          </p>
        </div>
      </div>
      {fields.length > 0 && (
        <dl className="linkedin-profile-fields">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {!email && (
        <p className="linkedin-profile-copy">
          LinkedIn did not provide a contact email. Enter the email the recruitment team should use below.
        </p>
      )}
      <div className="linkedin-profile-account">
        <span>LinkedIn account identifier</span>
        <code>{profile.sub}</code>
      </div>
    </section>
  );
}
