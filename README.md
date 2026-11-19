## Assignment 4 – Testing and DevOps Delivery

### Automated Backend Testing
- Backend tests are written using pytest.
- Tests cover DevOps status, invalid booking requests, missing ticket fields and sensor-event validation.
- Run tests locally using:

```bash
cd backend
python -m pytest -v
```

### Continuous Integration (GitHub Actions)
- GitHub Actions is configured to run automatically on pushes and pull requests to the `main` branch.
- The workflow installs Python dependencies and executes backend tests.
- Workflow file: `.github/workflows/ci.yml`
- The latest workflow run completed successfully.

### Docker Deployment Verification
The application runs using Docker Compose with three services:
- Backend – Flask/Gunicorn API
- Database – MySQL 8.4
- Proxy – Nginx 1.27

Verify running containers using:

```bash
docker compose ps
```

The frontend is accessible at:

http://localhost:8080

### Testing Evidence
Screenshots collected for submission:
- GitHub Actions successful workflow
- Docker containers running
- Application dashboard
- Application modules and DevOps integration hub
