export default function NotFound() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "2rem",
      }}
    >
      <section
        style={{
          maxWidth: "40rem",
          border: "1px solid rgba(17, 24, 39, 0.12)",
          borderRadius: "1.5rem",
          padding: "2rem",
          background: "rgba(255, 252, 245, 0.92)",
          boxShadow: "0 20px 50px rgba(23, 28, 39, 0.08)",
        }}
      >
        <p
          style={{
            margin: 0,
            fontSize: "0.78rem",
            textTransform: "uppercase",
            letterSpacing: "0.18em",
          }}
        >
          Not Found
        </p>
        <h1 style={{ margin: "1rem 0", fontSize: "2.5rem", lineHeight: 1 }}>
          This route does not exist.
        </h1>
        <p style={{ margin: 0, fontSize: "1rem", lineHeight: 1.6 }}>
          Return to the workbench to inspect the auditor service, publish a claim,
          or review the validation trail.
        </p>
      </section>
    </main>
  );
}
