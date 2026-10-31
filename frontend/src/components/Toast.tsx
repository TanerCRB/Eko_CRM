import "../styles/components.css";

interface ToastProps {
  message: string;
}

export function Toast({ message }: ToastProps) {
  return (
    <div className="toast visible" role="status" aria-live="polite" aria-atomic="true">
      {message}
    </div>
  );
}
