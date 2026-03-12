import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Proof-of-Audit",
  description: "Stake-backed smart contract audit attestations",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

