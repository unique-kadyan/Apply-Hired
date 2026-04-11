"use client";
import { useState, useEffect } from "react";
import api from "@/lib/api";
import styles from "@/lib/styles";

export default function ResumeOptimizer({ profile, setProfile, showToast }) {
  const [loading, setLoading] = useState(false);
  const [optimized, setOptimized] = useState(profile.optimized_resume || null);
  const [resumeScore, setResumeScore] = useState(profile.resume_score || null);
  const [hasPaid, setHasPaid] = useState(false);
  const [targetRole, setTargetRole] = useState(profile.title || "");
  const [targetCompany, setTargetCompany] = useState("");
  const [jobDesc, setJobDesc] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [priceLabel, setPriceLabel] = useState("");

  useEffect(() => {
    api.get("/api/payment/has-paid").then((r) => setHasPaid(r.paid));
    api
      .get("/api/payment/config")
      .then((r) => setPriceLabel(r.display_amount || ""));
    if (profile.optimized_resume) setOptimized(profile.optimized_resume);
    if (profile.resume_score) setResumeScore(profile.resume_score);
  }, [profile]);

  const startPayment = async () => {
    try {
      const config = await api.get("/api/payment/config");
      if (!config.configured) {
        showToast("Payment gateway not configured", "error");
        return;
      }
      const order = await api.post("/api/payment/create-order", {});
      if (order.error) {
        showToast(order.error, "error");
        return;
      }
      const options = {
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: "JobBot",
        description: "ATS Resume Optimization",
        order_id: order.order_id,
        handler: async (response) => {
          const verify = await api.post("/api/payment/verify", {
            order_id: response.razorpay_order_id,
            payment_id: response.razorpay_payment_id,
            signature: response.razorpay_signature,
          });
          if (verify.paid) {
            setHasPaid(true);
            showToast(
              "Payment successful! Now customize and optimize.",
              "success",
            );
            setShowForm(true);
          } else {
            showToast("Payment verification failed", "error");
          }
        },
        prefill: {
          name: profile.name,
          email: profile.email,
          contact: profile.phone,
        },
        theme: { color: "#2563eb" },
      };
      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err) {
      showToast("Payment failed. Please try again.", "error");
    }
  };

  const runOptimization = async () => {
    setLoading(true);
    showToast(
      "Optimizing your resume with AI... This may take 15-20 seconds.",
      "warning",
    );
    try {
      const res = await api.post("/api/payment/optimize-resume", {
        target_role: targetRole,
        target_company: targetCompany,
        job_description: jobDesc,
      });
      if (res.error) {
        showToast(res.error, "error");
      } else {
        setOptimized(res.optimized);
        if (res.resume_score) setResumeScore(res.resume_score);
        if (res.profile) setProfile(res.profile);
        showToast("Resume optimized!", "success");
        setShowForm(false);
      }
    } catch (err) {
      showToast("Optimization failed", "error");
    }
    setLoading(false);
  };

  const downloadPDF = async () => {
    const { default: jsPDF } = await import("jspdf");
    const doc = new jsPDF({ unit: "mm", format: "a4" });

    const pageW = 210;
    const margin = 18;
    const contentW = pageW - margin * 2;
    let y = 0;

    const addPage = () => {
      doc.addPage();
      y = margin;
    };

    const checkY = (needed = 8) => {
      if (y + needed > 280) addPage();
    };

    const line = (text, fontSize, color, bold, indent = 0, align = "left") => {
      doc.setFontSize(fontSize);
      doc.setTextColor(...color);
      doc.setFont("helvetica", bold ? "bold" : "normal");
      const x = margin + indent;
      const maxW = contentW - indent;
      const lines = doc.splitTextToSize(text, maxW);
      checkY(lines.length * fontSize * 0.4 + 2);
      doc.text(
        lines,
        align === "center" ? pageW / 2 : x,
        y,
        align === "center" ? { align: "center" } : {},
      );
      y += lines.length * fontSize * 0.4 + 1;
    };

    const rule = (r = 200, g = 200, b = 200) => {
      checkY(4);
      doc.setDrawColor(r, g, b);
      doc.line(margin, y, margin + contentW, y);
      y += 3;
    };

    const section = (title) => {
      y += 3;
      checkY(10);
      doc.setFontSize(10);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(37, 99, 235);
      doc.text(title.toUpperCase(), margin, y);
      y += 1.5;
      doc.setDrawColor(37, 99, 235);
      doc.setLineWidth(0.5);
      doc.line(margin, y, margin + contentW, y);
      doc.setLineWidth(0.2);
      y += 4;
    };

    doc.setFillColor(37, 99, 235);
    doc.rect(0, 0, pageW, 38, "F");

    y = 13;
    line(profile.name || "Your Name", 18, [255, 255, 255], true, 0, "center");
    y += 1;
    line(profile.title || "", 10, [186, 210, 255], false, 0, "center");
    y += 1;
    const contact = [profile.email, profile.phone, profile.location]
      .filter(Boolean)
      .join("  |  ");
    line(contact, 8.5, [186, 210, 255], false, 0, "center");
    y = 46;

    const links = [profile.linkedin_url, profile.github_url].filter(Boolean);
    if (links.length > 0) {
      line(links.join("  |  "), 8, [186, 210, 255], false, 0, "center");
    }
    y += 2;

    if (optimized.summary) {
      section("Professional Summary");
      line(optimized.summary, 9.5, [30, 30, 30], false);
    }

    const skills = optimized.skills || {};
    const skillGroups = Object.entries(skills).filter(
      ([, v]) => v && v.length > 0,
    );
    if (skillGroups.length > 0) {
      section("Skills");
      const labels = {
        languages: "Languages",
        backend: "Backend",
        frontend: "Frontend",
        databases: "Databases",
        cloud_devops: "Cloud & DevOps",
        architecture: "Architecture",
        testing: "Testing",
      };
      skillGroups.forEach(([key, vals]) => {
        checkY(6);
        doc.setFontSize(9);
        doc.setFont("helvetica", "bold");
        doc.setTextColor(60, 60, 60);
        const label = (labels[key] || key) + ": ";
        doc.text(label, margin, y);
        const lw = doc.getTextWidth(label);
        doc.setFont("helvetica", "normal");
        doc.setTextColor(30, 30, 30);
        const valText = vals.join(", ");
        const wrapped = doc.splitTextToSize(valText, contentW - lw);
        doc.text(wrapped, margin + lw, y);
        y += wrapped.length * 4 + 1.5;
      });
    }

    if ((optimized.experience || []).length > 0) {
      section("Experience");
      optimized.experience.forEach((exp) => {
        checkY(10);
        doc.setFontSize(10);
        doc.setFont("helvetica", "bold");
        doc.setTextColor(20, 20, 20);
        doc.text(exp.title || "", margin, y);
        if (exp.period) {
          doc.setFont("helvetica", "normal");
          doc.setTextColor(100, 100, 100);
          doc.setFontSize(8.5);
          const pw = doc.getTextWidth(exp.period);
          doc.text(exp.period, margin + contentW - pw, y);
        }
        y += 4.5;
        if (exp.company) line(exp.company, 9, [37, 99, 235], false);
        (exp.highlights || []).forEach((h) => {
          checkY(5);
          doc.setFontSize(8.8);
          doc.setFont("helvetica", "normal");
          doc.setTextColor(40, 40, 40);
          doc.text("\u2022", margin + 1, y);
          const hw = doc.splitTextToSize(h, contentW - 6);
          doc.text(hw, margin + 5, y);
          y += hw.length * 4 + 1;
        });
        y += 3;
      });
    }

    if (profile.education) {
      section("Education");
      line(profile.education, 9.5, [30, 30, 30], false);
    }

    if ((profile.certifications || []).length > 0) {
      section("Certifications");
      profile.certifications.forEach((c) =>
        line("\u2022  " + c, 9.5, [30, 30, 30], false),
      );
    }

    if ((optimized.ats_keywords || []).length > 0) {
      section("ATS Keywords");
      line(optimized.ats_keywords.join("  \u00b7  "), 9, [60, 60, 60], false);
    }

    const filename = `${(profile.name || "Resume").replace(/\s+/g, "_")}_Optimized_Resume.pdf`;
    doc.save(filename);
  };

  if (optimized && !showForm) {
    return (
      <div
        style={{
          background: "var(--bg2)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          padding: "1.5rem",
          marginBottom: "1rem",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
            flexWrap: "wrap",
            gap: "0.5rem",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
            }}
          >
            <h2
              style={{ fontSize: "1.1rem", margin: 0, color: "var(--green2)" }}
            >
              ATS-Optimized Resume
            </h2>
            {resumeScore && (
              <span
                style={{
                  background:
                    resumeScore.total_score >= 90
                      ? "#065f46"
                      : resumeScore.total_score >= 70
                        ? "#713f12"
                        : "#450a0a",
                  color:
                    resumeScore.total_score >= 90
                      ? "#6ee7b7"
                      : resumeScore.total_score >= 70
                        ? "#fcd34d"
                        : "#fca5a5",
                  padding: "0.2rem 0.75rem",
                  borderRadius: 20,
                  fontSize: "0.8rem",
                  fontWeight: 700,
                }}
              >
                {resumeScore.total_score}/100
              </span>
            )}
          </div>
          {profile.optimized_for && (
            <span style={{ color: "var(--muted)", fontSize: "0.78rem" }}>
              Tailored for: {profile.optimized_for.role}
              {profile.optimized_for.company
                ? ` at ${profile.optimized_for.company}`
                : ""}
            </span>
          )}
        </div>
        <div
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "1rem",
            marginBottom: "1rem",
          }}
        >
          <h3
            style={{
              fontSize: "0.85rem",
              color: "var(--muted)",
              marginBottom: "0.4rem",
            }}
          >
            Professional Summary
          </h3>
          <p style={{ color: "#cbd5e1", lineHeight: 1.7, margin: 0 }}>
            {optimized.summary}
          </p>
        </div>
        {(optimized.experience || []).map((exp, i) => (
          <div
            key={i}
            style={{
              marginBottom: "1rem",
              paddingBottom: "1rem",
              borderBottom:
                i < optimized.experience.length - 1
                  ? "1px solid var(--border)"
                  : "none",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                flexWrap: "wrap",
              }}
            >
              <strong style={{ color: "var(--text)" }}>{exp.title}</strong>
              <span style={{ color: "var(--muted)", fontSize: "0.82rem" }}>
                {exp.period}
              </span>
            </div>
            <p
              style={{
                color: "#60a5fa",
                fontSize: "0.88rem",
                marginBottom: "0.3rem",
              }}
            >
              {exp.company}
            </p>
            <ul
              style={{
                paddingLeft: "1.25rem",
                margin: 0,
                lineHeight: 1.8,
                color: "#cbd5e1",
                fontSize: "0.88rem",
              }}
            >
              {(exp.highlights || []).map((h, j) => (
                <li key={j}>{h}</li>
              ))}
            </ul>
          </div>
        ))}
        {optimized.ats_keywords && optimized.ats_keywords.length > 0 && (
          <div style={{ marginBottom: "1rem" }}>
            <h3
              style={{
                fontSize: "0.85rem",
                color: "var(--muted)",
                marginBottom: "0.4rem",
              }}
            >
              ATS Keywords Used
            </h3>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
              {optimized.ats_keywords.map((kw, i) => (
                <span
                  key={i}
                  style={{
                    background: "#065f46",
                    color: "#6ee7b7",
                    padding: "0.2rem 0.6rem",
                    borderRadius: 20,
                    fontSize: "0.78rem",
                  }}
                >
                  {kw}
                </span>
              ))}
            </div>
          </div>
        )}
        {optimized.optimization_notes &&
          optimized.optimization_notes.length > 0 && (
            <div
              style={{
                background: "rgba(37,99,235,0.08)",
                border: "1px solid rgba(37,99,235,0.2)",
                borderRadius: 10,
                padding: "1rem",
                marginBottom: "1rem",
              }}
            >
              <h3
                style={{
                  fontSize: "0.85rem",
                  color: "var(--accent2)",
                  margin: "0 0 0.4rem",
                }}
              >
                What We Improved
              </h3>
              <ul
                style={{
                  paddingLeft: "1.25rem",
                  margin: 0,
                  lineHeight: 1.7,
                  color: "#cbd5e1",
                  fontSize: "0.85rem",
                }}
              >
                {optimized.optimization_notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <button
            onClick={downloadPDF}
            style={{
              ...styles.btn,
              background: "linear-gradient(135deg, #059669, #065f46)",
              color: "#fff",
              fontSize: "0.88rem",
              padding: "0.55rem 1.25rem",
              fontWeight: 600,
            }}
          >
            Download PDF
          </button>
          <button
            onClick={() => {
              setShowForm(true);
              setOptimized(null);
            }}
            style={{
              ...styles.btn,
              ...styles.btnSecondary,
              fontSize: "0.85rem",
            }}
          >
            Re-optimize for a Different Role
          </button>
        </div>
      </div>
    );
  }

  if (hasPaid && (showForm || !optimized)) {
    return (
      <div
        style={{
          background: "var(--bg2)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          padding: "1.5rem",
          marginBottom: "1rem",
        }}
      >
        <h2 style={{ fontSize: "1.1rem", marginBottom: "0.3rem" }}>
          Optimize Your Resume
        </h2>
        <p
          style={{
            color: "var(--muted)",
            fontSize: "0.88rem",
            marginBottom: "1.25rem",
          }}
        >
          Tailor your resume for a specific role. Our AI will rewrite it for
          maximum ATS compatibility.
        </p>
        <div style={{ marginBottom: "1rem" }}>
          <label
            style={{
              display: "block",
              color: "var(--muted)",
              fontWeight: 600,
              marginBottom: "0.3rem",
              fontSize: "0.85rem",
            }}
          >
            Target Role
          </label>
          <input
            style={styles.input}
            value={targetRole}
            onChange={(e) => setTargetRole(e.target.value)}
            placeholder="e.g. Senior Backend Engineer"
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label
            style={{
              display: "block",
              color: "var(--muted)",
              fontWeight: 600,
              marginBottom: "0.3rem",
              fontSize: "0.85rem",
            }}
          >
            Target Company (optional)
          </label>
          <input
            style={styles.input}
            value={targetCompany}
            onChange={(e) => setTargetCompany(e.target.value)}
            placeholder="e.g. Google, Razorpay"
          />
        </div>
        <div style={{ marginBottom: "1.25rem" }}>
          <label
            style={{
              display: "block",
              color: "var(--muted)",
              fontWeight: 600,
              marginBottom: "0.3rem",
              fontSize: "0.85rem",
            }}
          >
            Paste Job Description (optional — improves keyword matching)
          </label>
          <textarea
            style={{ ...styles.input, minHeight: 120, resize: "vertical" }}
            value={jobDesc}
            onChange={(e) => setJobDesc(e.target.value)}
            placeholder="Paste the full job description here for best results..."
          />
        </div>
        <button
          onClick={runOptimization}
          disabled={loading || !targetRole}
          style={{
            ...styles.btn,
            ...styles.btnPrimary,
            padding: "0.7rem 2rem",
            fontSize: "0.95rem",
            opacity: !targetRole ? 0.5 : 1,
          }}
        >
          {loading ? "Optimizing..." : "Optimize Resume"}
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        background:
          "linear-gradient(135deg, rgba(37,99,235,0.1), rgba(124,58,237,0.1))",
        border: "1px solid rgba(37,99,235,0.3)",
        borderRadius: 14,
        padding: "1.5rem",
        marginBottom: "1rem",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: 1, minWidth: 250 }}>
          <h2
            style={{
              fontSize: "1.1rem",
              margin: "0 0 0.3rem",
              color: "var(--text)",
            }}
          >
            Fix &amp; Optimize Your Resume
          </h2>
          <p
            style={{
              color: "var(--muted)",
              fontSize: "0.88rem",
              lineHeight: 1.6,
              marginBottom: "1rem",
            }}
          >
            Get an AI-rewritten, ATS-optimized resume tailored for your target
            role. Includes:
          </p>
          <ul
            style={{
              paddingLeft: "1.25rem",
              margin: "0 0 1.25rem",
              lineHeight: 1.9,
              color: "#cbd5e1",
              fontSize: "0.88rem",
            }}
          >
            <li>ATS-friendly formatting and keywords</li>
            <li>Quantified achievements with strong action verbs</li>
            <li>Tailored to specific role and job description</li>
            <li>Professional summary rewrite</li>
            <li>Keyword optimization for recruiter search</li>
          </ul>
          <button
            onClick={startPayment}
            style={{
              ...styles.btn,
              background: "linear-gradient(135deg, #2563eb, #7c3aed)",
              color: "#fff",
              padding: "0.75rem 2rem",
              fontSize: "1rem",
              fontWeight: 700,
              boxShadow: "0 4px 15px rgba(37,99,235,0.3)",
            }}
          >
            {priceLabel ? `Optimize for ${priceLabel}` : "Optimize Resume"}
          </button>
          <p
            style={{
              color: "#64748b",
              fontSize: "0.75rem",
              marginTop: "0.5rem",
            }}
          >
            Per-optimization payment. Secure checkout via Razorpay.
          </p>
        </div>
      </div>
    </div>
  );
}
