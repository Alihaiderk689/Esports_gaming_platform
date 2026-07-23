import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ShieldCheck, Loader2, ArrowRight, Building2, CheckCircle2, Clock, XCircle, Upload, FileCheck2, PartyPopper, Wallet,
} from "lucide-react";
import { api } from "@/lib/api";

const STATUS_META = {
  pending: { label: "Under review", icon: Clock, className: "bg-muted text-muted-foreground" },
  approved: { label: "Approved", icon: CheckCircle2, className: "bg-primary/10 text-primary" },
  rejected: { label: "Rejected", icon: XCircle, className: "bg-destructive/10 text-destructive" },
};

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-heading font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${meta.className}`}>
      <meta.icon className="w-3.5 h-3.5" /> {meta.label}
    </span>
  );
}

function StatusInterstitial({ approved, companyName, reason, onContinue }) {
  return (
    <div className="max-w-lg mx-auto px-4 sm:px-6 py-16 sm:py-24 text-center">
      <div
        className={`w-16 h-16 rounded-2xl mx-auto grid place-items-center mb-6 ${
          approved ? "bg-gradient-to-br from-primary to-green-500 neon-border" : "bg-destructive/10 border border-destructive/30"
        }`}
      >
        {approved ? (
          <PartyPopper className="w-8 h-8 text-background" strokeWidth={2} />
        ) : (
          <XCircle className="w-8 h-8 text-destructive" strokeWidth={2} />
        )}
      </div>
      <h1 className={`font-display font-extrabold text-3xl mb-3 ${approved ? "gradient-text" : ""}`}>
        {approved ? "Congratulations!" : "Application not approved"}
      </h1>
      <p className="text-muted-foreground mb-8">
        {approved
          ? `${companyName ? `${companyName}, ` : ""}you're officially an organizer on Esports Pakistan. You can now create and run public tournaments.`
          : `Unfortunately, your organizer application was rejected.${reason ? ` Reason: ${reason}` : ""}`}
      </p>
      <button
        onClick={onContinue}
        className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow"
      >
        Click to continue <ArrowRight className="w-4 h-4" />
      </button>
    </div>
  );
}

function FileField({ label, value, onChange }) {
  return (
    <input
      type="file"
      required
      onChange={(e) => onChange(e.target.files?.[0] || null)}
      className="w-full text-xs text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-heading file:font-semibold"
      aria-label={label}
    />
  );
}

function ApplyForm({ onApplied }) {
  const [companyName, setCompanyName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [address, setAddress] = useState("");
  const [cnicNumber, setCnicNumber] = useState("");
  const [cnicFile, setCnicFile] = useState(null);
  const [companyRegNumber, setCompanyRegNumber] = useState("");
  const [companyFile, setCompanyFile] = useState(null);
  const [payoutMethod, setPayoutMethod] = useState("jazzcash");
  const [jazzcashNumber, setJazzcashNumber] = useState("");
  const [bankName, setBankName] = useState("");
  const [bankAccountTitle, setBankAccountTitle] = useState("");
  const [bankAccountNumber, setBankAccountNumber] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const payoutComplete = payoutMethod === "jazzcash"
    ? jazzcashNumber.trim()
    : bankName.trim() && bankAccountTitle.trim() && bankAccountNumber.trim();
  const canSubmit = companyName.trim() && cnicFile && companyFile && payoutComplete && !saving;

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError("");
    try {
      await api.post("/api/organizer/register/", {
        company_name: companyName,
        phone_number: phoneNumber,
        address,
        payout_method: payoutMethod,
        jazzcash_number: payoutMethod === "jazzcash" ? jazzcashNumber : "",
        bank_name: payoutMethod === "bank" ? bankName : "",
        bank_account_title: payoutMethod === "bank" ? bankAccountTitle : "",
        bank_account_number: payoutMethod === "bank" ? bankAccountNumber : "",
      }).catch((err) => {
        // Already registered means a previous attempt got this far before failing on a
        // later upload step — carry on and finish the document uploads instead of blocking.
        if (err.status !== 400) throw err;
      });

      const cnicForm = new FormData();
      if (cnicNumber.trim()) cnicForm.append("cnic_number", cnicNumber.trim());
      cnicForm.append("cnic_document", cnicFile);
      await api.post("/api/organizer/upload-cnic/", cnicForm, { formData: true });

      const companyForm = new FormData();
      if (companyRegNumber.trim()) companyForm.append("company_registration_number", companyRegNumber.trim());
      companyForm.append("company_document", companyFile);
      await api.post("/api/organizer/upload-company/", companyForm, { formData: true });

      const full = await api.get("/api/organizer/dashboard/");
      onApplied(full);
    } catch (err) {
      setError(err.message || "Could not submit your organizer application.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
      <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-green-500 grid place-items-center neon-border mb-5">
        <Building2 className="w-6 h-6 text-background" strokeWidth={2.5} />
      </div>
      <h2 className="font-display font-bold text-xl mb-1">Become an organizer</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Submit your details and verification documents. An admin will review everything together before approving you.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
            Company / organization name
          </label>
          <input
            required
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="e.g. FAST NUCES Esports Society"
            className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          />
        </div>
        <div>
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
            Phone number
          </label>
          <input
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            placeholder="Optional"
            className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          />
        </div>
        <div>
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
            Address
          </label>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Optional"
            className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          />
        </div>

        <div className="pt-2 border-t border-border/60">
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
            CNIC number (optional)
          </label>
          <input
            value={cnicNumber}
            onChange={(e) => setCnicNumber(e.target.value)}
            placeholder="e.g. 12345-1234567-1"
            className="w-full mb-3 px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          />
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
            CNIC document
          </label>
          <FileField label="CNIC document" value={cnicFile} onChange={setCnicFile} />
        </div>

        <div className="pt-2 border-t border-border/60">
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
            Company registration number (optional)
          </label>
          <input
            value={companyRegNumber}
            onChange={(e) => setCompanyRegNumber(e.target.value)}
            placeholder="Optional"
            className="w-full mb-3 px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          />
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
            Company document
          </label>
          <FileField label="Company document" value={companyFile} onChange={setCompanyFile} />
        </div>

        <div className="pt-2 border-t border-border/60">
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
            Payment method
          </label>
          <p className="text-xs text-muted-foreground mb-3">How you'd like to receive payouts from the platform.</p>
          <div className="flex gap-1 p-1 rounded-xl bg-muted/30 border border-border w-fit mb-3">
            {[{ value: "jazzcash", label: "JazzCash" }, { value: "bank", label: "Bank Account" }].map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setPayoutMethod(opt.value)}
                className={`px-3.5 py-1.5 rounded-lg text-sm font-heading font-semibold transition-colors ${
                  payoutMethod === opt.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {payoutMethod === "jazzcash" ? (
            <input
              required
              value={jazzcashNumber}
              onChange={(e) => setJazzcashNumber(e.target.value)}
              placeholder="JazzCash number, e.g. 03001234567"
              className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            />
          ) : (
            <div className="space-y-3">
              <input
                required
                value={bankName}
                onChange={(e) => setBankName(e.target.value)}
                placeholder="Bank name"
                className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
              />
              <input
                required
                value={bankAccountTitle}
                onChange={(e) => setBankAccountTitle(e.target.value)}
                placeholder="Account title"
                className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
              />
              <input
                required
                value={bankAccountNumber}
                onChange={(e) => setBankAccountNumber(e.target.value)}
                placeholder="Account number / IBAN"
                className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
              />
            </div>
          )}
        </div>

        {error && (
          <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-5 h-5 animate-spin" /> : <>Submit application <ArrowRight className="w-4 h-4" /></>}
        </button>
      </form>
    </div>
  );
}

function UploadCard({ title, desc, numberLabel, number, onNumberChange, uploaded, uploading, error, onUpload }) {
  const [file, setFile] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) return;
    await onUpload(file);
    setFile(null);
  };

  return (
    <div className="glass rounded-xl border border-border/60 p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-heading font-bold text-sm">{title}</h3>
        {uploaded && (
          <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary">
            <FileCheck2 className="w-3 h-3" /> Uploaded
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground mb-4">{desc}</p>
      <form onSubmit={submit} className="space-y-3">
        {numberLabel && (
          <input
            value={number}
            onChange={(e) => onNumberChange(e.target.value)}
            placeholder={numberLabel}
            className="w-full px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          />
        )}
        <input
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="w-full text-xs text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-heading file:font-semibold"
        />
        {error && (
          <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">{error}</div>
        )}
        <button
          type="submit"
          disabled={!file || uploading}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
        >
          {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {uploaded ? "Replace document" : "Upload"}
        </button>
      </form>
    </div>
  );
}

export default function Organizer() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null); // null (not yet applied) once loaded
  const [loadError, setLoadError] = useState("");

  const [profileForm, setProfileForm] = useState({ company_name: "", phone_number: "", address: "" });
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileSaved, setProfileSaved] = useState(false);

  const [cnicNumber, setCnicNumber] = useState("");
  const [cnicUploading, setCnicUploading] = useState(false);
  const [cnicError, setCnicError] = useState("");

  const [companyRegNumber, setCompanyRegNumber] = useState("");
  const [companyUploading, setCompanyUploading] = useState(false);
  const [companyError, setCompanyError] = useState("");

  const [payoutForm, setPayoutForm] = useState({
    payout_method: "jazzcash", jazzcash_number: "", bank_name: "", bank_account_title: "", bank_account_number: "",
  });
  const [payoutSaving, setPayoutSaving] = useState(false);
  const [payoutError, setPayoutError] = useState("");
  const [payoutSaved, setPayoutSaved] = useState(false);

  const applyProfile = (data) => {
    setProfile(data);
    setProfileForm({ company_name: data.company_name, phone_number: data.phone_number, address: data.address });
    setCnicNumber(data.cnic_number || "");
    setCompanyRegNumber(data.company_registration_number || "");
    setPayoutForm({
      payout_method: data.payout_method || "jazzcash",
      jazzcash_number: data.jazzcash_number || "",
      bank_name: data.bank_name || "",
      bank_account_title: data.bank_account_title || "",
      bank_account_number: data.bank_account_number || "",
    });
  };

  const load = async () => {
    setLoading(true);
    setLoadError("");
    try {
      await api.get("/api/organizer/status/");
      const full = await api.get("/api/organizer/dashboard/");
      applyProfile(full);
    } catch (e) {
      if (e.status === 404) setProfile(null);
      else setLoadError(e.message || "Could not load your organizer profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const saveProfile = async (e) => {
    e.preventDefault();
    setProfileSaving(true);
    setProfileError("");
    setProfileSaved(false);
    try {
      await api.patch("/api/organizer/profile/", profileForm);
      const full = await api.get("/api/organizer/dashboard/");
      applyProfile(full);
      setProfileSaved(true);
    } catch (err) {
      setProfileError(err.message || "Could not update your profile.");
    } finally {
      setProfileSaving(false);
    }
  };

  const savePayout = async (e) => {
    e.preventDefault();
    setPayoutSaving(true);
    setPayoutError("");
    setPayoutSaved(false);
    try {
      await api.patch("/api/organizer/profile/", payoutForm);
      const full = await api.get("/api/organizer/dashboard/");
      applyProfile(full);
      setPayoutSaved(true);
    } catch (err) {
      setPayoutError(err.message || "Could not update your payment details.");
    } finally {
      setPayoutSaving(false);
    }
  };

  const uploadCnic = async (file) => {
    setCnicUploading(true);
    setCnicError("");
    try {
      const formData = new FormData();
      if (cnicNumber.trim()) formData.append("cnic_number", cnicNumber.trim());
      formData.append("cnic_document", file);
      const updated = await api.post("/api/organizer/upload-cnic/", formData, { formData: true });
      applyProfile(updated);
    } catch (err) {
      setCnicError(err.message || "Could not upload your CNIC.");
    } finally {
      setCnicUploading(false);
    }
  };

  const uploadCompanyDoc = async (file) => {
    setCompanyUploading(true);
    setCompanyError("");
    try {
      const formData = new FormData();
      if (companyRegNumber.trim()) formData.append("company_registration_number", companyRegNumber.trim());
      formData.append("company_document", file);
      const updated = await api.post("/api/organizer/upload-company/", formData, { formData: true });
      applyProfile(updated);
    } catch (err) {
      setCompanyError(err.message || "Could not upload your company document.");
    } finally {
      setCompanyUploading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
          {loadError}
        </p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="max-w-lg mx-auto px-4 sm:px-6 py-12 sm:py-16">
        <ApplyForm onApplied={applyProfile} />
      </div>
    );
  }

  const hasUnseenOutcome = profile.status !== "pending" && profile.status !== profile.last_seen_status;

  if (hasUnseenOutcome) {
    const approved = profile.status === "approved";
    const acknowledgeAndContinue = async () => {
      try {
        await api.post("/api/organizer/status/acknowledge/", {});
      } catch {
        /* best-effort — still take them onward */
      }
      navigate(approved ? "/dashboard" : "/");
    };
    return (
      <StatusInterstitial
        approved={approved}
        companyName={profile.company_name}
        reason={profile.rejection_reason}
        onContinue={acknowledgeAndContinue}
      />
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-12 sm:py-16 space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="font-display font-extrabold text-3xl gradient-text">Organizer Profile</h1>
          <StatusBadge status={profile.status} />
        </div>
        <p className="text-sm text-muted-foreground">{profile.company_name}</p>
      </div>

      {profile.status === "pending" && (
        <div className="glass rounded-2xl border border-border/60 p-8 text-center">
          <Clock className="w-10 h-10 text-primary mx-auto mb-4" />
          <h2 className="font-display font-bold text-2xl mb-2">Your application is under review</h2>
          <p className="text-sm text-muted-foreground">
            An admin is reviewing your details and documents. You can still update your information below while you wait.
          </p>
        </div>
      )}
      {profile.status === "rejected" && profile.rejection_reason && (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-4 py-3">
          <span className="font-heading font-semibold">Reason: </span>{profile.rejection_reason}
        </div>
      )}

      <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
        <div className="flex items-center gap-2 mb-1">
          <ShieldCheck className="w-5 h-5 text-primary" />
          <h2 className="font-display font-bold text-xl">Profile details</h2>
        </div>
        <p className="text-sm text-muted-foreground mb-6">Update your organization's contact information.</p>

        <form onSubmit={saveProfile} className="space-y-4">
          <div>
            <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Company / organization name
            </label>
            <input
              required
              value={profileForm.company_name}
              onChange={(e) => setProfileForm((f) => ({ ...f, company_name: e.target.value }))}
              className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Phone number
            </label>
            <input
              value={profileForm.phone_number}
              onChange={(e) => setProfileForm((f) => ({ ...f, phone_number: e.target.value }))}
              className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Address
            </label>
            <input
              value={profileForm.address}
              onChange={(e) => setProfileForm((f) => ({ ...f, address: e.target.value }))}
              className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            />
          </div>

          {profileError && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {profileError}
            </div>
          )}
          {profileSaved && (
            <div className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
              Profile updated.
            </div>
          )}

          <button
            type="submit"
            disabled={profileSaving}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-50"
          >
            {profileSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save changes"}
          </button>
        </form>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <UploadCard
          title="CNIC"
          desc="Upload a photo or scan of your national ID card for verification."
          numberLabel="CNIC number (optional)"
          number={cnicNumber}
          onNumberChange={setCnicNumber}
          uploaded={profile.cnic_uploaded}
          uploading={cnicUploading}
          error={cnicError}
          onUpload={uploadCnic}
        />
        <UploadCard
          title="Company document"
          desc="Upload proof of your organization (registration certificate, letterhead, etc.)."
          numberLabel="Registration number (optional)"
          number={companyRegNumber}
          onNumberChange={setCompanyRegNumber}
          uploaded={profile.company_document_uploaded}
          uploading={companyUploading}
          error={companyError}
          onUpload={uploadCompanyDoc}
        />
      </div>

      <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
        <div className="flex items-center gap-2 mb-1">
          <Wallet className="w-5 h-5 text-primary" />
          <h2 className="font-display font-bold text-xl">Bank account</h2>
        </div>
        <p className="text-sm text-muted-foreground mb-6">How you receive payouts from the platform.</p>

        <form onSubmit={savePayout} className="space-y-4">
          <div className="flex gap-1 p-1 rounded-xl bg-muted/30 border border-border w-fit">
            {[{ value: "jazzcash", label: "JazzCash" }, { value: "bank", label: "Bank Account" }].map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setPayoutForm((f) => ({ ...f, payout_method: opt.value }))}
                className={`px-3.5 py-1.5 rounded-lg text-sm font-heading font-semibold transition-colors ${
                  payoutForm.payout_method === opt.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {payoutForm.payout_method === "jazzcash" ? (
            <div>
              <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
                JazzCash number
              </label>
              <input
                required
                value={payoutForm.jazzcash_number}
                onChange={(e) => setPayoutForm((f) => ({ ...f, jazzcash_number: e.target.value }))}
                placeholder="e.g. 03001234567"
                className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
              />
            </div>
          ) : (
            <>
              <div>
                <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
                  Bank name
                </label>
                <input
                  required
                  value={payoutForm.bank_name}
                  onChange={(e) => setPayoutForm((f) => ({ ...f, bank_name: e.target.value }))}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
                  Account title
                </label>
                <input
                  required
                  value={payoutForm.bank_account_title}
                  onChange={(e) => setPayoutForm((f) => ({ ...f, bank_account_title: e.target.value }))}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
                  Account number / IBAN
                </label>
                <input
                  required
                  value={payoutForm.bank_account_number}
                  onChange={(e) => setPayoutForm((f) => ({ ...f, bank_account_number: e.target.value }))}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
                />
              </div>
            </>
          )}

          {payoutError && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {payoutError}
            </div>
          )}
          {payoutSaved && (
            <div className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
              Payment details updated.
            </div>
          )}

          <button
            type="submit"
            disabled={payoutSaving}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-50"
          >
            {payoutSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save changes"}
          </button>
        </form>
      </div>
    </div>
  );
}
