# Smart Campus Facility Booking and Maintenance Platform

Educational full-stack prototype based on Assignment 3.

## Features
- Facility catalogue and booking submission
- Server-side overlapping-booking check using a database transaction and facility-row lock
- Restricted booking approval workflow
- Maintenance tickets with explainable keyword-based category/priority suggestions
- Controlled sensor-event intake with event-ID deduplication
- Ticket lifecycle, inspection notes, resolution and role-gated closure
- Audit history and local DevOps integration demonstration
- Docker Compose deployment with MySQL persistence and Nginx reverse proxy

## Requirements
Install Docker Desktop (Windows/Mac) or Docker Engine + Compose (Linux), and VS Code.

## Run
1. Open this folder in VS Code.
2. Copy `.env.example` to `.env` and change both passwords.
3. In the project terminal run:

   ```bash
   docker compose up --build -d
   docker compose ps
   ```

4. Open http://localhost:8080
5. Check API health at http://localhost:8080/api/health

## Stop / restart
```bash
docker compose down
docker compose up -d
```
Database records persist in the `mysql_data` volume. To intentionally erase all database data:
```bash
docker compose down -v
```

## Two backend instances (Q6 experiment)
```bash
docker compose up --build -d --scale backend=2
docker compose ps
```
The Nginx proxy sends API requests to the backend service. Both instances use the same MySQL database.

## Useful tests
- Create a booking, then create another booking for the same facility with overlapping times. The second must be rejected with HTTP 409.
- Create a restricted booking and approve/reject it in the Approvals page.
- Create a ticket and move it through its lifecycle.
- Click the sensor alert button twice. The second request uses the same event ID and should not create a second ticket.
- Restart backend containers and confirm bookings/tickets remain.

## API examples
Create ticket:
```bash
curl -X POST http://localhost:8080/api/tickets \
-H "Content-Type: application/json" \
-d '{"title":"Broken light","description":"Light is not working","reported_by":"Faculty"}'
```
Sensor event:
```bash
curl -X POST http://localhost:8080/api/sensor-events \
-H "Content-Type: application/json" \
-d '{"event_id":"SENSOR-100","title":"Leak alert","description":"Water leak near lab","reported_by":"Sensor"}'
```

## Important limitations / honest reporting
- This is a demonstration prototype, not production-ready authentication. The UI uses demo actors and role values; implement real login/session or token-based authentication before claiming secure identity verification.
- Ticket suggestions are deterministic keyword rules, not trained AI/ML.
- Sensor monitoring is simulated; no physical IoT device is connected.
- DevOps integration is a local illustrative record; no external issue tracker is connected.
- The workload and concurrency tests must be run and recorded; do not claim a user capacity without measured evidence.
- MySQL locking and transactions protect the demonstrated booking path. For stronger production-grade ticket concurrency, add client-supplied version checks / optimistic locking and test race conditions.
- The MySQL initialization script runs only when the database volume is first created. Use `docker compose down -v` only if you want to reset all data.
