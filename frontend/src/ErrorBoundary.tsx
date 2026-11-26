import { Component, ReactNode } from "react";

/** Contains a render crash to one panel so the rest of the dashboard keeps working. */
export default class ErrorBoundary extends Component<{ label: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { console.error(`Panel "${this.props.label}" crashed:`, error); }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="card error" role="alert">
        <strong>{this.props.label} could not be displayed.</strong> The rest of the app is unaffected.
        <div><button onClick={() => this.setState({ failed: false })}>Try again</button></div>
      </div>
    );
  }
}
