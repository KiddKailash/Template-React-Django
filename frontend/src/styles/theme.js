/**
 * Global Theme Configuration.
 *
 * Palette values live in DESIGN.md. Update both together — never introduce
 * hex colours outside this file (CLAUDE.md rule).
 */

import { createTheme } from '@mui/material/styles';

const PALETTE = {
  light: {
    primary: {
      main: '#2563EB',
      dark: '#1D4ED8',
      light: '#3B82F6',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#0F172A',
      dark: '#0B1120',
      light: '#334155',
      contrastText: '#ffffff',
    },
    success: { main: '#16A34A', dark: '#15803D', light: '#22C55E', contrastText: '#ffffff' },
    warning: { main: '#D97706', dark: '#B45309', light: '#F59E0B', contrastText: '#ffffff' },
    error: { main: '#DC2626', dark: '#B91C1C', light: '#EF4444', contrastText: '#ffffff' },
    info: { main: '#2563EB', dark: '#1D4ED8', light: '#3B82F6', contrastText: '#ffffff' },
    background: {
      default: '#FFFFFF',
      paper: '#F8FAFC',
    },
    text: {
      primary: '#0F172A',
      secondary: '#64748B',
      disabled: '#94A3B8',
    },
    divider: '#E2E8F0',
  },
  dark: {
    primary: {
      main: '#3B82F6',
      dark: '#2563EB',
      light: '#60A5FA',
      contrastText: '#0F172A',
    },
    secondary: {
      main: '#F1F5F9',
      dark: '#CBD5E1',
      light: '#FFFFFF',
      contrastText: '#0F172A',
    },
    success: { main: '#22C55E', dark: '#16A34A', light: '#4ADE80', contrastText: '#0F172A' },
    warning: { main: '#F59E0B', dark: '#D97706', light: '#FBBF24', contrastText: '#0F172A' },
    error: { main: '#EF4444', dark: '#DC2626', light: '#F87171', contrastText: '#0F172A' },
    info: { main: '#3B82F6', dark: '#2563EB', light: '#60A5FA', contrastText: '#0F172A' },
    background: {
      default: '#0F172A',
      paper: '#1E293B',
    },
    text: {
      primary: '#F1F5F9',
      secondary: '#94A3B8',
      disabled: '#64748B',
    },
    divider: '#334155',
  },
};

const TYPOGRAPHY = {
  fontFamily: [
    '-apple-system',
    'BlinkMacSystemFont',
    '"Segoe UI"',
    'Roboto',
    '"Helvetica Neue"',
    'Arial',
    'sans-serif',
  ].join(','),
  h1: { fontWeight: 600 },
  h2: { fontWeight: 600 },
  h3: { fontWeight: 600 },
  h4: { fontWeight: 600 },
  h5: { fontWeight: 600 },
  h6: { fontWeight: 600 },
  button: { textTransform: 'none', fontWeight: 500 },
};

const SHAPE = {
  borderRadius: 8,
};

export const getTheme = (mode = 'light') =>
  createTheme({
    palette: {
      mode,
      ...PALETTE[mode],
    },
    typography: TYPOGRAPHY,
    shape: SHAPE,
    components: {
      MuiButton: {
        defaultProps: { disableElevation: true },
      },
      MuiCard: {
        defaultProps: { elevation: 0 },
        styleOverrides: {
          root: ({ theme }) => ({
            border: `1px solid ${theme.palette.divider}`,
          }),
        },
      },
    },
  });

export default getTheme;
