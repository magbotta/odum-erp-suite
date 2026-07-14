import { createBrowserRouter } from 'react-router-dom';
import AppShell from './shell/AppShell';
import LoginPage from './auth/LoginPage';
import DashboardPage from './pages/DashboardPage';
import EntityPage from './pages/EntityPage';
import ProfilePage from './pages/ProfilePage';
import AgentHandoffInboxPage from './pages/AgentHandoffInboxPage';
import NotFoundPage from './pages/NotFoundPage';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      {
        path: 'profile',
        element: <ProfilePage />,
      },
      {
        path: 'agents/handoffs',
        element: <AgentHandoffInboxPage />,
      },
      {
        path: 'entities/:app/:entity',
        element: <EntityPage mode="list" />,
      },
      {
        path: 'entities/:app/:entity/new',
        element: <EntityPage mode="new" />,
      },
      {
        path: 'entities/:app/:entity/:id',
        element: <EntityPage mode="detail" />,
      },
      {
        path: 'entities/:app/:entity/:id/edit',
        element: <EntityPage mode="edit" />,
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);
