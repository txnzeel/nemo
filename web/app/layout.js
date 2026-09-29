import "./globals.css";
export const metadata = {
  title: "NEMO · Evidence to decisions",
  description: "Evidence-driven growth intelligence",
};
export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
