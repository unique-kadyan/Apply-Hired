"use client";
import { useState, useRef } from "react";
import api from "@/lib/api";
import styles from "@/lib/styles";
import ConnectAccounts from "./ConnectAccounts";
import ExperienceSection from "./ExperienceSection";

export default function Profile({ profile, setProfile, showToast }) {
  const fileRef = useRef(null);
  const avatarRef = useRef(null);
  const jsonRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [avatarHover, setAvatarHover] = useState(false);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [jsonParsing, setJsonParsing] = useState(false);
  const [noticePeriod, setNoticePeriod] = useState(profile.notice_period || "");
  const [salaryMin, setSalaryMin] = useState(profile.expected_salary_min || "");
  const [salaryMax, setSalaryMax] = useState(profile.expected_salary_max || "");
  const [salaryCurrency, setSalaryCurrency] = useState(
    profile.expected_salary_currency || "INR",
  );
  const [salaryPeriod, setSalaryPeriod] = useState(
    profile.expected_salary_period || "annually",
  );
  const [prefSaving, setPrefSaving] = useState(false);
  const _prefSaved = !!(
    profile.notice_period ||
    profile.expected_salary_min ||
    profile.expected_salary_max
  );
  const [prefEditing, setPrefEditing] = useState(!_prefSaved);
  const [linkedinUrl, setLinkedinUrl] = useState(profile.linkedin_url || "");
  const [githubUrl, setGithubUrl] = useState(profile.github_url || "");
  const [linksSaving, setLinksSaving] = useState(false);

  const uploadAvatar = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setAvatarUploading(true);
    const fd = new FormData();
    fd.append("avatar", file);
    try {
      const res = await api.upload("/api/profile/upload-avatar", fd);
      if (res.error) showToast(res.error, "error");
      else {
        setProfile(res.profile);
        showToast("Profile picture updated!", "success");
      }
    } catch (err) {
      showToast("Upload failed", "error");
    }
    setAvatarUploading(false);
    e.target.value = "";
  };

  const uploadResume = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("resume", file);
    try {
      const res = await api.upload("/api/profile/upload-resume", fd);
      if (res.error) {
        showToast(res.error, "error");
      } else {
        setProfile(res.profile);
        showToast("Resume parsed successfully! Profile updated.", "success");
      }
    } catch (err) {
      showToast("Upload failed", "error");
    }
    setUploading(false);
    e.target.value = "";
  };

  const parseResumeJson = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setJsonParsing(true);
    const fd = new FormData();
    fd.append("resume", file);
    try {
      const res = await api.upload("/api/profile/parse-resume-json", fd);
      if (res.error) {
        showToast(res.error, "error");
      } else {
        const blob = new Blob([JSON.stringify(res.data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "resume_structured.json";
        a.click();
        URL.revokeObjectURL(url);
        showToast("Structured JSON downloaded!", "success");
      }
    } catch (err) {
      showToast("Parsing failed", "error");
    }
    setJsonParsing(false);
    e.target.value = "";
  };

  const saveLinks = async () => {
    setLinksSaving(true);
    try {
      const res = await api.put("/api/profile", {
        linkedin_url: linkedinUrl,
        github_url: githubUrl,
      });
      if (res.error) showToast(res.error, "error");
      else {
        setProfile(res);
        showToast("Profile links saved!", "success");
      }
    } catch {
      showToast("Save failed", "error");
    }
    setLinksSaving(false);
  };

  const savePreferences = async () => {
    setPrefSaving(true);
    try {
      const res = await api.put("/api/profile", {
        notice_period: noticePeriod,
        expected_salary_min: salaryMin !== "" ? Number(salaryMin) : null,
        expected_salary_max: salaryMax !== "" ? Number(salaryMax) : null,
        expected_salary_currency: salaryCurrency,
        expected_salary_period: salaryPeriod,
      });
      if (res.error) showToast(res.error, "error");
      else {
        setProfile(res);
        showToast("Job preferences saved!", "success");
      }
    } catch (err) {
      showToast("Save failed", "error");
    }
    setPrefSaving(false);
  };

  return (
    <div style={styles.container}>
      <h1 style={{ fontSize: "1.5rem", marginBottom: "1.5rem" }}>Profile</h1>

      <div style={styles.card}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "1.5rem",
            marginBottom: "1.5rem",
            flexWrap: "wrap",
          }}
        >
          <div
            role="button"
            title="Click to change profile picture"
            onClick={() => !avatarUploading && avatarRef.current.click()}
            onMouseEnter={() => setAvatarHover(true)}
            onMouseLeave={() => setAvatarHover(false)}
            style={{
              position: "relative",
              width: 82,
              height: 82,
              borderRadius: "50%",
              flexShrink: 0,
              cursor: "pointer",
            }}
          >
            {profile.avatar ? (
              <img
                src={profile.avatar}
                alt="Profile"
                style={{
                  width: 82,
                  height: 82,
                  borderRadius: "50%",
                  objectFit: "cover",
                  display: "block",
                  border:
                    "3px solid " +
                    (avatarHover ? "var(--accent2)" : "transparent"),
                  transition: "border-color 0.2s",
                  filter: avatarHover ? "brightness(0.65)" : "none",
                }}
              />
            ) : (
              <div
                style={{
                  width: 82,
                  height: 82,
                  background: "linear-gradient(135deg, #2563eb, #7c3aed)",
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "2rem",
                  fontWeight: 700,
                  color: "#fff",
                  border:
                    "3px solid " +
                    (avatarHover ? "var(--accent2)" : "transparent"),
                  filter: avatarHover ? "brightness(0.7)" : "none",
                  transition: "all 0.2s",
                }}
              >
                {(profile.name || "U")[0].toUpperCase()}
              </div>
            )}
            {(avatarHover || avatarUploading) && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: "50%",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  pointerEvents: "none",
                }}
              >
                <span style={{ fontSize: avatarUploading ? "1rem" : "1.4rem" }}>
                  {avatarUploading ? "⏳" : "📷"}
                </span>
                <span
                  style={{
                    fontSize: "0.6rem",
                    color: "#fff",
                    fontWeight: 600,
                    marginTop: 2,
                  }}
                >
                  {avatarUploading ? "Uploading" : "Change"}
                </span>
              </div>
            )}
            <input
              ref={avatarRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              onChange={uploadAvatar}
              style={{ display: "none" }}
            />
          </div>
          <div>
            <h2 style={{ margin: 0, marginBottom: "0.2rem" }}>
              {profile.name || "Your Name"}
            </h2>
            <p style={{ color: "#60a5fa" }}>{profile.title || "Your Title"}</p>
            <p style={{ color: "var(--muted)", fontSize: "0.88rem" }}>
              {profile.location} | {profile.years_of_experience} yrs |{" "}
              {profile.open_to}
            </p>
            <p style={{ color: "var(--muted)", fontSize: "0.88rem" }}>
              {profile.email} | {profile.phone}
            </p>
          </div>
        </div>
        <p style={{ lineHeight: 1.7, color: "#cbd5e1" }}>{profile.summary}</p>
      </div>

      <div style={styles.card}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "0.5rem",
            marginBottom: "0.5rem",
          }}
        >
          <h2 style={{ fontSize: "1.1rem", margin: 0 }}>Upload Resume</h2>
          {profile.profile_updated_at && (
            <span
              style={{
                fontSize: "0.78rem",
                color: "var(--muted)",
                background: "var(--bg3)",
                padding: "0.2rem 0.6rem",
                borderRadius: 6,
                display: "flex",
                alignItems: "center",
                gap: "0.3rem",
              }}
            >
              &#128336; Last updated:{" "}
              {new Date(profile.profile_updated_at).toLocaleString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
        </div>
        <p
          style={{
            color: "var(--muted)",
            marginBottom: "1rem",
            fontSize: "0.9rem",
          }}
        >
          Upload your resume (PDF, DOCX, TXT) and your profile will be
          auto-parsed.
        </p>
        <div
          style={{
            display: "flex",
            gap: "0.75rem",
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={uploadResume}
            style={{ display: "none" }}
          />
          <button
            style={{ ...styles.btn, ...styles.btnPrimary }}
            onClick={() => fileRef.current.click()}
            disabled={uploading}
          >
            {uploading ? "⏳ Parsing resume..." : "📤 Upload & Parse"}
          </button>
          <input
            ref={jsonRef}
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={parseResumeJson}
            style={{ display: "none" }}
          />
          <button
            style={{
              ...styles.btn,
              background: "rgba(16,185,129,0.12)",
              color: "#34d399",
              border: "1px solid rgba(16,185,129,0.3)",
            }}
            onClick={() => jsonRef.current.click()}
            disabled={jsonParsing}
            title="Parse resume and download as standardised JSON"
          >
            {jsonParsing ? "⏳ Generating..." : "⬇ Export as JSON"}
          </button>
          <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            PDF, DOCX, TXT
          </span>
        </div>
      </div>

      <div style={styles.card}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "0.75rem",
          }}
        >
          <div>
            <h2 style={{ fontSize: "1.1rem", margin: "0 0 0.15rem" }}>
              Profile Links
            </h2>
            <p style={{ color: "var(--muted)", fontSize: "0.8rem", margin: 0 }}>
              Required for a 100/100 resume score
            </p>
          </div>
          {(profile.linkedin_url || profile.github_url) && (
            <span
              style={{
                background: "#065f46",
                color: "#6ee7b7",
                padding: "0.15rem 0.6rem",
                borderRadius: 20,
                fontSize: "0.72rem",
                fontWeight: 600,
              }}
            >
              +4 pts
            </span>
          )}
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "0.75rem",
            marginBottom: "0.75rem",
          }}
        >
          <div>
            <label
              style={{
                display: "block",
                color: "var(--muted)",
                fontSize: "0.8rem",
                fontWeight: 600,
                marginBottom: "0.3rem",
              }}
            >
              LinkedIn URL
            </label>
            <input
              style={styles.input}
              value={linkedinUrl}
              onChange={(e) => setLinkedinUrl(e.target.value)}
              placeholder="linkedin.com/in/yourname"
            />
          </div>
          <div>
            <label
              style={{
                display: "block",
                color: "var(--muted)",
                fontSize: "0.8rem",
                fontWeight: 600,
                marginBottom: "0.3rem",
              }}
            >
              GitHub URL
            </label>
            <input
              style={styles.input}
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              placeholder="github.com/yourname"
            />
          </div>
        </div>
        <button
          onClick={saveLinks}
          disabled={linksSaving}
          style={{
            ...styles.btn,
            ...styles.btnPrimary,
            fontSize: "0.85rem",
            opacity: linksSaving ? 0.6 : 1,
          }}
        >
          {linksSaving ? "Saving..." : "Save Links"}
        </button>
      </div>

      <ConnectAccounts
        profile={profile}
        setProfile={setProfile}
        showToast={showToast}
      />

      <div style={styles.card}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: prefEditing ? "1.2rem" : "1rem",
          }}
        >
          <h2 style={{ fontSize: "1.1rem", margin: 0 }}>Job Preferences</h2>
          {!prefEditing && (
            <button
              onClick={() => setPrefEditing(true)}
              style={{
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--text2)",
                borderRadius: 8,
                padding: "0.35rem 0.85rem",
                cursor: "pointer",
                fontSize: "0.82rem",
                fontWeight: 500,
                display: "flex",
                alignItems: "center",
                gap: "0.35rem",
                transition: "all 0.15s",
              }}
            >
              ✏️ Edit
            </button>
          )}
        </div>

        {prefEditing ? (
          <>
            <div style={{ marginBottom: "1.5rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 600,
                  color: "var(--muted)",
                  fontSize: "0.8rem",
                  marginBottom: "0.7rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                }}
              >
                Notice Period
              </label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                {[
                  "Immediate",
                  "15 days",
                  "30 days",
                  "45 days",
                  "60 days",
                  "90 days",
                ].map((opt) => (
                  <label
                    key={opt}
                    onClick={() => setNoticePeriod(opt)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.4rem",
                      cursor: "pointer",
                      padding: "0.4rem 0.9rem",
                      borderRadius: 20,
                      border:
                        "1px solid " +
                        (noticePeriod === opt ? "#3b82f6" : "var(--border)"),
                      background:
                        noticePeriod === opt
                          ? "rgba(59,130,246,0.15)"
                          : "transparent",
                      color: noticePeriod === opt ? "#60a5fa" : "var(--text2)",
                      fontSize: "0.87rem",
                      fontWeight: noticePeriod === opt ? 600 : 400,
                      transition: "all 0.15s",
                      userSelect: "none",
                    }}
                  >
                    <span
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        border:
                          "2px solid " +
                          (noticePeriod === opt ? "#3b82f6" : "#475569"),
                        background:
                          noticePeriod === opt ? "#3b82f6" : "transparent",
                        display: "inline-block",
                        flexShrink: 0,
                        transition: "all 0.15s",
                      }}
                    />
                    {opt}
                  </label>
                ))}
              </div>
            </div>
            <div style={{ marginBottom: "1.5rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 600,
                  color: "var(--muted)",
                  fontSize: "0.8rem",
                  marginBottom: "0.7rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                }}
              >
                Expected Compensation
              </label>
              <div
                style={{
                  display: "flex",
                  gap: "0.65rem",
                  flexWrap: "wrap",
                  alignItems: "center",
                }}
              >
                <select
                  value={salaryCurrency}
                  onChange={(e) => setSalaryCurrency(e.target.value)}
                  style={{
                    ...styles.input,
                    width: 90,
                    padding: "0.5rem 0.5rem",
                  }}
                >
                  {["INR", "USD", "EUR", "GBP", "AED", "SGD"].map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
                <input
                  type="number"
                  placeholder="Min"
                  value={salaryMin}
                  onChange={(e) => setSalaryMin(e.target.value)}
                  style={{
                    ...styles.input,
                    width: 120,
                    padding: "0.5rem 0.7rem",
                  }}
                  min={0}
                />
                <span style={{ color: "var(--muted)", fontSize: "1.1rem" }}>
                  –
                </span>
                <input
                  type="number"
                  placeholder="Max"
                  value={salaryMax}
                  onChange={(e) => setSalaryMax(e.target.value)}
                  style={{
                    ...styles.input,
                    width: 120,
                    padding: "0.5rem 0.7rem",
                  }}
                  min={0}
                />
                <div
                  style={{
                    display: "flex",
                    borderRadius: 8,
                    overflow: "hidden",
                    border: "1px solid var(--border)",
                  }}
                >
                  {["monthly", "annually"].map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setSalaryPeriod(p)}
                      style={{
                        padding: "0.45rem 0.85rem",
                        background:
                          salaryPeriod === p ? "#3b82f6" : "transparent",
                        color: salaryPeriod === p ? "#fff" : "var(--muted)",
                        border: "none",
                        cursor: "pointer",
                        fontSize: "0.84rem",
                        fontWeight: salaryPeriod === p ? 600 : 400,
                        transition: "all 0.15s",
                      }}
                    >
                      {p.charAt(0).toUpperCase() + p.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
              {(salaryMin || salaryMax) && (
                <p
                  style={{
                    color: "#94a3b8",
                    fontSize: "0.8rem",
                    marginTop: "0.5rem",
                  }}
                >
                  {`${salaryCurrency} ${salaryMin && salaryMax ? `${Number(salaryMin).toLocaleString()} – ${Number(salaryMax).toLocaleString()}` : salaryMin ? `from ${Number(salaryMin).toLocaleString()}` : `up to ${Number(salaryMax).toLocaleString()}`} / ${salaryPeriod}`}
                </p>
              )}
            </div>
            <div
              style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}
            >
              <button
                onClick={async () => {
                  await savePreferences();
                  setPrefEditing(false);
                }}
                disabled={prefSaving}
                style={{ ...styles.btn, ...styles.btnPrimary }}
              >
                {prefSaving ? "Saving\u2026" : "Save Preferences"}
              </button>
              {_prefSaved && (
                <button
                  type="button"
                  onClick={() => setPrefEditing(false)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--muted)",
                    cursor: "pointer",
                    fontSize: "0.85rem",
                    padding: "0.4rem 0.5rem",
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </>
        ) : (
          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}
          >
            {noticePeriod && (
              <div
                style={{ display: "flex", alignItems: "center", gap: "1rem" }}
              >
                <span
                  style={{
                    fontSize: "0.78rem",
                    fontWeight: 600,
                    color: "var(--muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    minWidth: 130,
                  }}
                >
                  Notice Period
                </span>
                <span
                  style={{
                    background: "rgba(59,130,246,0.12)",
                    color: "#60a5fa",
                    padding: "0.3rem 0.9rem",
                    borderRadius: 20,
                    fontSize: "0.87rem",
                    fontWeight: 600,
                    border: "1px solid rgba(59,130,246,0.25)",
                  }}
                >
                  {noticePeriod}
                </span>
              </div>
            )}
            {(salaryMin || salaryMax) && (
              <div
                style={{ display: "flex", alignItems: "center", gap: "1rem" }}
              >
                <span
                  style={{
                    fontSize: "0.78rem",
                    fontWeight: 600,
                    color: "var(--muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    minWidth: 130,
                  }}
                >
                  Compensation
                </span>
                <span
                  style={{
                    color: "#e2e8f0",
                    fontSize: "0.95rem",
                    fontWeight: 500,
                  }}
                >
                  {`${salaryCurrency} ${salaryMin && salaryMax ? `${Number(salaryMin).toLocaleString()} – ${Number(salaryMax).toLocaleString()}` : salaryMin ? `from ${Number(salaryMin).toLocaleString()}` : `up to ${Number(salaryMax).toLocaleString()}`}`}
                  <span
                    style={{
                      color: "var(--muted)",
                      fontSize: "0.82rem",
                      marginLeft: "0.4rem",
                    }}
                  >
                    / {salaryPeriod}
                  </span>
                </span>
              </div>
            )}
            {!noticePeriod && !salaryMin && !salaryMax && (
              <p
                style={{
                  color: "var(--muted)",
                  fontSize: "0.88rem",
                  margin: 0,
                }}
              >
                No preferences set yet.
              </p>
            )}
          </div>
        )}
      </div>

      <div style={styles.card}>
        <h2 style={{ fontSize: "1.1rem", marginBottom: "0.75rem" }}>
          Technical Skills
        </h2>
        {profile.skills &&
          Object.entries(profile.skills).map(([group, skills]) => (
            <div key={group} style={{ marginBottom: "1rem" }}>
              <h3
                style={{
                  fontSize: "0.8rem",
                  color: "var(--muted)",
                  textTransform: "uppercase",
                  marginBottom: "0.4rem",
                  letterSpacing: "0.05em",
                }}
              >
                {group.replace(/_/g, " ")}
              </h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                {skills.map((s, i) => (
                  <span
                    key={i}
                    style={{
                      background: "#1e3a5f",
                      color: "#93c5fd",
                      padding: "0.3rem 0.8rem",
                      borderRadius: 20,
                      fontSize: "0.83rem",
                      fontWeight: 500,
                    }}
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          ))}
      </div>

      <ExperienceSection experience={profile.experience || []} />

      <div style={styles.card}>
        <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
          Education
        </h2>
        <p style={{ color: "#cbd5e1" }}>{profile.education}</p>
      </div>

      {profile.certifications && profile.certifications.length > 0 && (
        <div style={styles.card}>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.75rem" }}>
            Certifications
          </h2>
          <ul
            style={{ paddingLeft: "1.5rem", lineHeight: 1.8, color: "#cbd5e1" }}
          >
            {profile.certifications.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {profile.achievements && profile.achievements.length > 0 && (
        <div style={styles.card}>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.75rem" }}>
            Achievements
          </h2>
          <ul
            style={{ paddingLeft: "1.5rem", lineHeight: 1.8, color: "#cbd5e1" }}
          >
            {profile.achievements.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
