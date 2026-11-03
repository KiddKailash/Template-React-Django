import { Component } from 'react';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import RefreshIcon from '@mui/icons-material/Refresh';

/** Catches a render exception in the routed content instead of white-screening
 * the whole app (from Store-Arbitrage).
 *
 * A class component because getDerivedStateFromError / componentDidCatch have
 * no hook equivalent. `resetKey` (the current pathname) clears the error when
 * the user navigates, so one broken page does not leave the app stuck here.
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prevProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error, info) {
    // No error-reporting service by default, so the console is the report,
    // with the component stack: the message alone rarely names the screen.
    console.error('Unhandled render error', error, info?.componentStack);
  }

  handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <Box sx={{ width: '100%', mx: 'auto', py: 4 }}>
        <Alert severity="error" variant="outlined">
          <AlertTitle>This page hit a problem</AlertTitle>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Something on this screen failed to render. Nothing was saved or lost.
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} useFlexGap>
            <Button
              variant="contained"
              size="small"
              startIcon={<RefreshIcon />}
              onClick={this.handleReset}
            >
              Try again
            </Button>
            <Button size="small" href="/">
              Go to Home
            </Button>
          </Stack>
          <Typography
            component="pre"
            variant="caption"
            sx={{
              color: 'text.secondary',
              mt: 2,
              mb: 0,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            }}
          >
            {String(this.state.error?.message || this.state.error)}
          </Typography>
        </Alert>
      </Box>
    );
  }
}

export default ErrorBoundary;
