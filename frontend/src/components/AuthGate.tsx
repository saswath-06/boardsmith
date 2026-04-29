// Sign-in screen shown when no Supabase session exists.
// Single Google OAuth button — same visual language as the splash.
import AmbientPcb from "./AmbientPcb";
import BoardsmithLogo from "./Logo";
import { useAuth } from "../lib/auth";

const GoogleGlyph = () => (
  <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden>
    <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.6-6 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.7 1.1 7.8 3l5.7-5.7C34 6.5 29.3 4.5 24 4.5 13.2 4.5 4.5 13.2 4.5 24S13.2 43.5 24 43.5c11 0 19.5-8 19.5-19.5 0-1.3-.1-2.3-.4-3.5z"/>
    <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.6 16.1 19 13 24 13c3 0 5.7 1.1 7.8 3l5.7-5.7C34 6.5 29.3 4.5 24 4.5c-7.6 0-14.2 4.3-17.7 10.7z"/>
    <path fill="#4CAF50" d="M24 43.5c5.2 0 10-2 13.5-5.2l-6.2-5.2c-2 1.4-4.5 2.3-7.3 2.3-5.3 0-9.7-3.4-11.3-8L6 32.4C9.4 39 16.1 43.5 24 43.5z"/>
    <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.1 4.1-3.9 5.5l6.2 5.2c.5-.5 7-5.1 7-15.2 0-1.3-.1-2.3-.4-3.5z"/>
  </svg>
);

const AuthGate = () => {
  const { signInWithGoogle, loading } = useAuth();

  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center px-6 py-16 overflow-hidden bs-bg-grid">
      <AmbientPcb />

      <div className="relative z-10 w-full max-w-md flex flex-col items-center text-center">
        <div className="flex items-center gap-3 mb-8">
          <BoardsmithLogo size={48} />
          <div className="flex flex-col items-start">
            <span
              className="text-[26px] font-semibold tracking-tight leading-none"
              style={{ color: "var(--bs-fg)" }}
            >
              Boardsmith
            </span>
            <span
              className="font-mono text-[10px] mt-1 uppercase tracking-[0.2em]"
              style={{ color: "var(--bs-copper)" }}
            >
              PCB · forged in plain English
            </span>
          </div>
        </div>

        <div
          className="mb-6 inline-flex items-center gap-2 px-3 py-1 rounded-full font-mono text-[11px]"
          style={{
            border: "1px solid var(--bs-line)",
            background: "var(--bs-bg-2)",
            color: "var(--bs-fg-mute)",
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full bs-pulse"
            style={{ background: "var(--bs-copper)" }}
          />
          <span style={{ color: "var(--bs-copper)" }}>SIGN IN REQUIRED</span>
        </div>

        <h1
          className="mb-4 max-w-md text-[36px] leading-[1.05] font-semibold tracking-tight"
          style={{ color: "var(--bs-fg)" }}
        >
          Welcome to Boardsmith
        </h1>

        <p
          className="mb-8 max-w-sm text-[14px] leading-relaxed"
          style={{ color: "var(--bs-fg-mute)" }}
        >
          Sign in with Google to start designing PCBs from natural language.
          Your jobs, refinements, and BOMs are saved to your account.
        </p>

        <button
          onClick={() => void signInWithGoogle()}
          disabled={loading}
          className="bs-btn-primary px-5 py-3 rounded flex items-center justify-center gap-3 text-[14px] font-medium disabled:opacity-50"
          style={{ minWidth: 260 }}
        >
          <GoogleGlyph />
          Continue with Google
        </button>

        <div
          className="mt-8 font-mono text-[10px]"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          By signing in you agree to use Boardsmith for hobby PCB design only.
        </div>
      </div>

      <div
        className="absolute bottom-4 left-0 right-0 flex justify-between px-6 font-mono text-[10px] uppercase tracking-widest z-10"
        style={{ color: "var(--bs-fg-dim)" }}
      >
        <span>boardsmith · 2026</span>
        <span>natural language → fr4 · in seconds</span>
      </div>
    </section>
  );
};

export default AuthGate;
