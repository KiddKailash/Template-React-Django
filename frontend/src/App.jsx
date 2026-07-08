import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

// Contexts
import { UserProvider } from './contexts/UserContext';
import { SnackbarProvider } from './contexts/SnackbarContext';

// Components
import PrivateRoute from './components/PrivateRoute';

// Pages
import Home from './pages/Home';
import AuthPage from './pages/AuthPage';
import Error404 from './pages/Error404';

// MUI
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';

function AppContent() {
  return (
    <Box sx={{ display: 'flex', minHeight: '100dvh', bgcolor: 'background.default' }}>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          bgcolor: 'background.paper',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Container
          maxWidth="xl"
          sx={{ my: 1.5, display: 'flex', flexDirection: 'column', flexGrow: 1 }}
          aria-label="Main Content"
        >
          <Routes>
            <Route path="/login" element={<AuthPage />} />
            <Route
              path="/"
              element={
                <PrivateRoute>
                  <Home />
                </PrivateRoute>
              }
            />
            <Route
              path="*"
              element={
                <PrivateRoute>
                  <Error404 />
                </PrivateRoute>
              }
            />
          </Routes>
        </Container>
      </Box>
    </Box>
  );
}

function App() {
  return (
    <Router>
      <SnackbarProvider>
        <UserProvider>
          <AppContent />
        </UserProvider>
      </SnackbarProvider>
    </Router>
  );
}

export default App;
