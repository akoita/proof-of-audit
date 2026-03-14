export default function Legacy404Page() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "2rem",
        fontFamily: "'Inter', sans-serif",
        background: "#f6f1e8",
        color: "#142447",
      }}
    >
      <section
        style={{
          maxWidth: "40rem",
          border: "1px solid rgba(20, 36, 71, 0.12)",
          borderRadius: "1.5rem",
          padding: "2rem",
          background: "rgba(255, 255, 255, 0.86)",
          boxShadow: "0 18px 50px rgba(20, 36, 71, 0.08)",
        }}
      >
        <p
          style={{
            margin: 0,
            fontSize: "0.8rem",
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
          or review a validation trail.
        </p>
      </section>
    </main>
  );
}
