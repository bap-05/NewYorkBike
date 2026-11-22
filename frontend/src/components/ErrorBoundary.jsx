import { Component } from "react";

export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  retry = () => this.setState({ failed: false });

  render() {
    return this.state.failed
      ? this.props.fallback(this.retry)
      : this.props.children;
  }
}
