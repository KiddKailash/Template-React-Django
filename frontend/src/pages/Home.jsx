import { useContext } from 'react';

import UserContext from '../contexts/UserContext';

// MUI
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

const Home = () => {
  const { user } = useContext(UserContext);

  return (
    <Box sx={{ py: 6 }}>
      <Card elevation={0} sx={{ border: 1, borderColor: 'divider' }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h4">Template App</Typography>
            <Typography variant="body1" color="text.secondary">
              This is the Django + React template landing page. Replace it with your
              app's home screen.
            </Typography>

            {user && (
              <Typography variant="body2" color="text.secondary">
                Signed in as <strong>{user.username}</strong> ({user.email || 'no email'}).
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};

export default Home;
