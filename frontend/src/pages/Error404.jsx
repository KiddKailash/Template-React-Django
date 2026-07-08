import { useNavigate } from 'react-router-dom';

// MUI
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

const Error404 = () => {
  const navigate = useNavigate();

  return (
    <Box
      maxWidth="xs"
      sx={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100%',
      }}
    >
      <Stack direction="column" spacing={1}>
        <Typography variant="caption" color="error">
          Error 404
        </Typography>
        <Typography variant="h5" gutterBottom>
          Page Not Found
        </Typography>
        <Button variant="contained" color="primary" onClick={() => navigate('/')}>
          Go home
        </Button>
      </Stack>
    </Box>
  );
};

export default Error404;
