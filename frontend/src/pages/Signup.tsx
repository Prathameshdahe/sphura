import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AuthLayout } from "@/components/auth/auth-layout";
import { EMAIL_RE, Field, FormError, SubmitButton } from "@/components/auth/auth-form";
import { GoogleSignIn } from "@/components/auth/google-button";
import { api, errorMessage } from "@/lib/api";
import { firstName } from "@/lib/format";
import { qk } from "@/lib/queries";

export default function Signup() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ name?: string; email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const next: typeof errors = {};
    if (!name.trim()) next.name = "Tell us what to call you";
    if (!EMAIL_RE.test(email.trim())) next.email = "Enter a valid email address";
    if (password.length < 8) next.password = "Use at least 8 characters";
    setErrors(next);
    setFormError(null);
    if (Object.keys(next).length) return;
    setLoading(true);
    try {
      const user = await api.register({ name: name.trim(), email: email.trim(), password });
      qc.setQueryData(qk.me, user);
      toast.success(`Welcome to Sphura, ${firstName(user.name) || "friend"}!`);
      navigate("/", { replace: true });
    } catch (err) {
      setFormError(errorMessage(err, "Couldn't create your account"));
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Keep your chats, documents and dashboards in one place."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <GoogleSignIn />
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <FormError message={formError} />
        <Field label="Name" value={name} onChange={setName} error={errors.name} autoComplete="name" autoFocus />
        <Field label="Email" type="email" value={email} onChange={setEmail} error={errors.email} autoComplete="email" />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          error={errors.password}
          autoComplete="new-password"
          hint="At least 8 characters."
        />
        <SubmitButton loading={loading}>{loading ? "Creating account…" : "Create account"}</SubmitButton>
      </form>
    </AuthLayout>
  );
}
