import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Matrimony deployment assistant",
  description: "Documentation-grounded deployment steps for the Matrimony server. Nothing is executed for you.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
