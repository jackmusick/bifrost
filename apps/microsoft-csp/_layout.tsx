// Root layout wrapper - full height with overflow control
export default function RootLayout() {
  return (
    <div className="h-full bg-background overflow-hidden">
      <Outlet />
    </div>
  );
}
