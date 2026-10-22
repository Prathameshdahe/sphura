import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AuthLayout } from "@/components/auth/auth-layout";
import { EMAIL_RE, Field, FormError, SubmitButton } from "@/components/auth/auth-form";
import { GoogleSignIn } from "@/components/auth/google-button";
import { api, errorMessage, returnPath } from "@/lib/api";
import { qk } from "@/lib/queries";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const next: typeof errors = {};
    if (!EMAIL_RE.test(email.trim())) next.email = "Enter a valid email address";
    if (!password) next.password = "Enter your password";
    setErrors(next);
    setFormError(null);
    if (Object.keys(next).length) return;
    setLoading(true);
    try {
      const user = await api.login({ email: email.trim(), password });
      qc.setQueryData(qk.me, user);
      navigate(returnPath(location.state), { replace: true });
    } catch (err) {
      setFormError(errorMessage(err, "Couldn't sign you in"));
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to continue to Sphura."
      footer={
        <>
          New to Sphura?{" "}
          <Link to="/signup" className="font-medium text-foreground underline-offset-4 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <GoogleSignIn />
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <FormError message={formError} />
        <Field label="Email" type="email" value={email} onChange={setEmail} error={errors.email} autoComplete="email" autoFocus />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          error={errors.password}
          autoComplete="current-password"
        />
        <SubmitButton loading={loading}>{loading ? "Signing in…" : "Sign in"}</SubmitButton>
      </form>
    </AuthLayout>
  );
}
